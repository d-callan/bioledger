from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import ChatMessage, LedgerEntry, LedgerSession

SCHEMA_VERSION = 1  # bump when schema changes

_SCHEMA_V1 = """\
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created TEXT NOT NULL,
    updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entries (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    kind TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    data TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    forge TEXT NOT NULL DEFAULT '',
    entry_id TEXT DEFAULT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
CREATE INDEX IF NOT EXISTS idx_entries_session ON entries(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_session ON chat_messages(session_id);
"""

# Sequential migrations: version N → N+1
_MIGRATIONS: dict[int, str] = {
    # 1: "ALTER TABLE sessions ADD COLUMN tags TEXT DEFAULT '';",
}


def _get_schema_version(conn: sqlite3.Connection) -> int:
    """Read current schema version, or 0 if DB is brand new."""
    try:
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        return row[0] if row and row[0] is not None else 0
    except sqlite3.OperationalError:
        return 0  # table doesn't exist yet


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Apply any pending schema migrations sequentially."""
    current = _get_schema_version(conn)
    if current == 0:
        # Fresh DB — apply full schema
        conn.executescript(_SCHEMA_V1)
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()
        return
    while current < SCHEMA_VERSION:
        next_ver = current + 1
        if next_ver not in _MIGRATIONS:
            raise RuntimeError(
                f"No migration from schema version {current} to {next_ver}"
            )
        conn.executescript(_MIGRATIONS[next_ver])
        conn.execute("UPDATE schema_version SET version = ?", (next_ver,))
        conn.commit()
        current = next_ver


class LedgerStore:
    """SQLite-backed ledger persistence. Atomic, append-only, concurrent-read-safe.
    Schema migrations are applied automatically on init."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or Path.home() / ".bioledger" / "ledger.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")  # WAL for concurrent reads
        _run_migrations(self._conn)

    def create_session(self, session: LedgerSession) -> None:
        """Create a new session (no entries yet)."""
        self._conn.execute(
            "INSERT INTO sessions (id, name, description, status, created, updated) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                session.id,
                session.name,
                session.description,
                session.status.value,
                session.created.isoformat(),
                session.updated.isoformat(),
            ),
        )
        self._conn.commit()

    def append_entry(self, session_id: str, entry: LedgerEntry) -> None:
        """Append a single entry to a session. Atomic."""
        self._conn.execute(
            "INSERT INTO entries (id, session_id, kind, timestamp, data) VALUES (?, ?, ?, ?, ?)",
            (
                entry.id,
                session_id,
                entry.kind.value,
                entry.timestamp.isoformat(),
                entry.model_dump_json(),
            ),
        )
        self._touch_session(session_id)
        self._conn.commit()

    def append_message(self, session_id: str, msg: ChatMessage) -> None:
        """Append a chat message to a session. Atomic."""
        self._conn.execute(
            "INSERT INTO chat_messages (id, session_id, role, content, timestamp, forge, entry_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                msg.id,
                session_id,
                msg.role,
                msg.content,
                msg.timestamp.isoformat(),
                msg.forge,
                msg.entry_id,
            ),
        )
        self._touch_session(session_id)
        self._conn.commit()

    def load_session(
        self,
        session_id: str,
        include_messages: bool = True,
        max_entries: int | None = None,
        max_messages: int | None = None,
    ) -> LedgerSession:
        """Load a session with entries and optionally chat messages.

        Args:
            session_id: Session to load
            include_messages: Whether to load chat messages
            max_entries: If set, load only the N most recent entries (for large sessions)
            max_messages: If set, load only the N most recent messages
        """
        row = self._conn.execute(
            "SELECT id, name, description, status, created, updated "
            "FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            raise KeyError(f"Session '{session_id}' not found")
        session = LedgerSession(
            id=row[0],
            name=row[1],
            description=row[2],
            status=row[3],
            created=row[4],
            updated=row[5],
        )

        # Load entries (optionally capped)
        if max_entries is not None:
            # Get most recent N, but preserve chronological order
            entry_query = (
                "SELECT data FROM ("
                "  SELECT data, timestamp FROM entries WHERE session_id = ? "
                "  ORDER BY timestamp DESC LIMIT ?"
                ") ORDER BY timestamp ASC"
            )
            entry_rows = self._conn.execute(
                entry_query, (session_id, max_entries)
            ).fetchall()
        else:
            entry_query = (
                "SELECT data FROM entries WHERE session_id = ? ORDER BY timestamp"
            )
            entry_rows = self._conn.execute(entry_query, (session_id,)).fetchall()
        session.entries = [LedgerEntry.model_validate_json(r[0]) for r in entry_rows]

        if include_messages:
            if max_messages is not None:
                msg_query = (
                    "SELECT id, role, content, timestamp, forge, entry_id FROM ("
                    "  SELECT id, role, content, timestamp, forge, entry_id "
                    "  FROM chat_messages WHERE session_id = ? "
                    "  ORDER BY timestamp DESC LIMIT ?"
                    ") ORDER BY timestamp ASC"
                )
                msg_rows = self._conn.execute(
                    msg_query, (session_id, max_messages)
                ).fetchall()
            else:
                msg_query = (
                    "SELECT id, role, content, timestamp, forge, entry_id "
                    "FROM chat_messages WHERE session_id = ? ORDER BY timestamp"
                )
                msg_rows = self._conn.execute(msg_query, (session_id,)).fetchall()
            session.chat_messages = [
                ChatMessage(
                    id=r[0], role=r[1], content=r[2], timestamp=r[3], forge=r[4], entry_id=r[5]
                )
                for r in msg_rows
            ]
        return session

    def list_sessions(self, status: str | None = None) -> list[dict[str, str]]:
        """List sessions with basic metadata. Optionally filter by status."""
        if status:
            rows = self._conn.execute(
                "SELECT id, name, description, status, created, updated "
                "FROM sessions WHERE status = ? ORDER BY updated DESC",
                (status,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, name, description, status, created, updated "
                "FROM sessions ORDER BY updated DESC"
            ).fetchall()
        return [
            {
                "id": r[0],
                "name": r[1],
                "description": r[2],
                "status": r[3],
                "created": r[4],
                "updated": r[5],
            }
            for r in rows
        ]

    def rename_session(self, session_id: str, name: str) -> None:
        """Rename a session."""
        self._conn.execute(
            "UPDATE sessions SET name = ? WHERE id = ?", (name, session_id)
        )
        self._touch_session(session_id)
        self._conn.commit()

    def update_session_description(self, session_id: str, description: str) -> None:
        """Update a session's description."""
        self._conn.execute(
            "UPDATE sessions SET description = ? WHERE id = ?",
            (description, session_id),
        )
        self._touch_session(session_id)
        self._conn.commit()

    def archive_session(self, session_id: str) -> None:
        """Archive a session (soft-delete). Still queryable."""
        self._conn.execute(
            "UPDATE sessions SET status = 'archived' WHERE id = ?", (session_id,)
        )
        self._conn.commit()

    def message_count(self, session_id: str) -> int:
        """Return the number of chat messages in a session."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE session_id = ?", (session_id,)
        ).fetchone()
        return row[0] if row else 0

    def save_session(self, session: LedgerSession) -> None:
        """Persist a session's current state: upsert session row, append any new
        entries and chat messages not yet in the DB. Safe to call repeatedly."""
        # Upsert session metadata
        self._conn.execute(
            "INSERT INTO sessions (id, name, description, status, created, updated) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, "
            "description=excluded.description, status=excluded.status, "
            "updated=excluded.updated",
            (
                session.id,
                session.name,
                session.description,
                session.status.value,
                session.created.isoformat(),
                session.updated.isoformat(),
            ),
        )
        # Append entries not yet persisted (INSERT OR IGNORE by PK)
        for entry in session.entries:
            self._conn.execute(
                "INSERT OR IGNORE INTO entries (id, session_id, kind, timestamp, data) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    entry.id,
                    session.id,
                    entry.kind.value,
                    entry.timestamp.isoformat(),
                    entry.model_dump_json(),
                ),
            )
        # Append messages not yet persisted
        for msg in session.chat_messages:
            self._conn.execute(
                "INSERT OR IGNORE INTO chat_messages "
                "(id, session_id, role, content, timestamp, forge, entry_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    msg.id,
                    session.id,
                    msg.role,
                    msg.content,
                    msg.timestamp.isoformat(),
                    msg.forge,
                    msg.entry_id,
                ),
            )
        self._conn.commit()

    def _touch_session(self, session_id: str) -> None:
        """Update the session's updated timestamp."""
        self._conn.execute(
            "UPDATE sessions SET updated = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), session_id),
        )

    def close(self) -> None:
        self._conn.close()
