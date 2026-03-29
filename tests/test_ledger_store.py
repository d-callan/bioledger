from __future__ import annotations

from bioledger.ledger.models import (
    ChatMessage,
    EntryKind,
    LedgerEntry,
    LedgerSession,
    SessionStatus,
)
from bioledger.ledger.store import LedgerStore


def test_create_and_load_session(tmp_db_path):
    store = LedgerStore(db_path=tmp_db_path)
    session = LedgerSession(name="Test", description="A test session")
    store.create_session(session)

    loaded = store.load_session(session.id)
    assert loaded.id == session.id
    assert loaded.name == "Test"
    assert loaded.description == "A test session"
    assert loaded.status == SessionStatus.ACTIVE


def test_save_session_with_entries(tmp_db_path):
    store = LedgerStore(db_path=tmp_db_path)
    session = LedgerSession(name="With entries")
    store.create_session(session)

    entry = LedgerEntry(kind=EntryKind.TOOL_RUN, tool_spec_name="fastqc", exit_code=0)
    session.add(entry)
    store.save_session(session)

    loaded = store.load_session(session.id)
    assert len(loaded.entries) == 1
    assert loaded.entries[0].tool_spec_name == "fastqc"


def test_list_sessions(tmp_db_path):
    store = LedgerStore(db_path=tmp_db_path)
    s1 = LedgerSession(name="First")
    s2 = LedgerSession(name="Second")
    store.create_session(s1)
    store.create_session(s2)

    rows = store.list_sessions()
    assert len(rows) == 2
    names = {r["name"] for r in rows}
    assert "First" in names
    assert "Second" in names


def test_list_sessions_filter_by_status(tmp_db_path):
    store = LedgerStore(db_path=tmp_db_path)
    s1 = LedgerSession(name="Active")
    store.create_session(s1)
    store.archive_session(s1.id)

    s2 = LedgerSession(name="Still active")
    store.create_session(s2)

    active = store.list_sessions(status="active")
    assert len(active) == 1
    assert active[0]["name"] == "Still active"

    all_sessions = store.list_sessions(status=None)
    assert len(all_sessions) == 2


def test_rename_session(tmp_db_path):
    store = LedgerStore(db_path=tmp_db_path)
    session = LedgerSession(name="Old name")
    store.create_session(session)

    store.rename_session(session.id, "New name")
    loaded = store.load_session(session.id)
    assert loaded.name == "New name"


def test_update_session_description(tmp_db_path):
    store = LedgerStore(db_path=tmp_db_path)
    session = LedgerSession(name="Test")
    store.create_session(session)

    store.update_session_description(session.id, "Updated description")
    loaded = store.load_session(session.id)
    assert loaded.description == "Updated description"


def test_archive_session(tmp_db_path):
    store = LedgerStore(db_path=tmp_db_path)
    session = LedgerSession(name="To archive")
    store.create_session(session)

    store.archive_session(session.id)
    loaded = store.load_session(session.id)
    assert loaded.status == SessionStatus.ARCHIVED


def test_append_and_load_messages(tmp_db_path):
    store = LedgerStore(db_path=tmp_db_path)
    session = LedgerSession(name="Chat test")
    store.create_session(session)

    msg = ChatMessage(role="user", content="Hello", forge="test")
    store.append_message(session.id, msg)

    msg2 = ChatMessage(role="assistant", content="Hi there", forge="test")
    store.append_message(session.id, msg2)

    loaded = store.load_session(session.id, include_messages=True)
    assert len(loaded.chat_messages) == 2
    assert loaded.chat_messages[0].role == "user"
    assert loaded.chat_messages[1].role == "assistant"


def test_message_count(tmp_db_path):
    store = LedgerStore(db_path=tmp_db_path)
    session = LedgerSession(name="Count test")
    store.create_session(session)

    assert store.message_count(session.id) == 0

    store.append_message(session.id, ChatMessage(role="user", content="Hi"))
    store.append_message(session.id, ChatMessage(role="assistant", content="Hello"))
    assert store.message_count(session.id) == 2


def test_load_session_without_messages(tmp_db_path):
    store = LedgerStore(db_path=tmp_db_path)
    session = LedgerSession(name="No messages")
    store.create_session(session)
    store.append_message(session.id, ChatMessage(role="user", content="Hi"))

    loaded = store.load_session(session.id, include_messages=False)
    assert len(loaded.chat_messages) == 0
