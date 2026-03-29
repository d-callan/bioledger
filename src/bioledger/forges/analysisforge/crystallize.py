from __future__ import annotations

import logging
from collections import defaultdict

from bioledger.ledger.models import EntryKind, LedgerEntry, LedgerSession

logger = logging.getLogger(__name__)


def _build_dag(
    session: LedgerSession,
) -> tuple[
    dict[str | None, list[LedgerEntry]],  # parent_id → children
    dict[str, LedgerEntry],  # id → entry
]:
    """Build adjacency list from parent_id links."""
    children: dict[str | None, list[LedgerEntry]] = defaultdict(list)
    by_id: dict[str, LedgerEntry] = {}
    for entry in session.entries:
        if entry.kind in (EntryKind.TOOL_RUN, EntryKind.SCRIPT_RUN):
            children[entry.parent_id].append(entry)
            by_id[entry.id] = entry
    return children, by_id


def _topological_order(
    children: dict[str | None, list[LedgerEntry]],
) -> list[LedgerEntry]:
    """Topological sort respecting parent_id dependencies."""
    visited: set[str] = set()
    order: list[LedgerEntry] = []

    def dfs(entry: LedgerEntry) -> None:
        if entry.id in visited:
            return
        visited.add(entry.id)
        for child in children.get(entry.id, []):
            dfs(child)
        order.append(entry)

    # Start from root entries (parent_id is None)
    for root_entry in children.get(None, []):
        dfs(root_entry)
    return list(reversed(order))


def _proc_name(entry: LedgerEntry, index: int) -> str:
    """Generate a Nextflow process name from a ledger entry."""
    base = entry.tool_spec_name or (
        entry.container.image.split("/")[-1].split(":")[0] if entry.container else "unknown"
    )
    return f"step_{index}_{base}".replace("-", "_")


def _make_nf_process(proc: str, entry: LedgerEntry) -> str:
    """Build a single Nextflow process block from a ledger entry."""
    image = entry.container.image if entry.container else "ubuntu:latest"
    cmd = " ".join(entry.container.command) if entry.container else "echo 'no command'"
    return f"""
process {proc} {{
    container '{image}'

    input:
    path input_files

    output:
    path '*'

    script:
    \"\"\"
    {cmd}
    \"\"\"
}}"""


def to_nextflow(session: LedgerSession) -> str:
    """Convert a ledger session into a DAG-aware Nextflow DSL2 workflow."""
    children, by_id = _build_dag(session)
    ordered = _topological_order(children)

    if not ordered:
        return "// Empty workflow — no tool or script runs in session"

    entry_to_proc: dict[str, str] = {}
    processes: list[str] = []
    workflow_lines: list[str] = [
        "workflow {",
        "    ch_input = Channel.fromPath(params.input)",
    ]

    for i, entry in enumerate(ordered):
        proc = _proc_name(entry, i)
        entry_to_proc[entry.id] = proc
        processes.append(_make_nf_process(proc, entry))

        # Wire inputs: root entries get ch_input, others get parent's output
        if entry.parent_id is None or entry.parent_id not in entry_to_proc:
            workflow_lines.append(f"    {proc}(ch_input)")
        else:
            parent_proc = entry_to_proc[entry.parent_id]
            workflow_lines.append(f"    {proc}({parent_proc}.out)")

    workflow_lines.append("}")
    return "\n".join(processes) + "\n\n" + "\n".join(workflow_lines)


def to_nextflow_from_entries(entries: list[LedgerEntry]) -> str:
    """Generate a Nextflow DSL2 workflow from a list of entries (not a full session).

    Used by build_rocrate when user selects specific entries to package.
    Builds DAG from the provided entries only, treating entries whose
    parent_id is not in the subset as root entries.

    Returns:
        Nextflow DSL2 workflow string. Includes a comment warning if the
        selection contains disconnected subgraphs (multiple roots).
    """
    tool_entries = [
        e for e in entries if e.kind in (EntryKind.TOOL_RUN, EntryKind.SCRIPT_RUN)
    ]
    if not tool_entries:
        return "// Empty workflow — no tool or script runs in selection"

    entry_to_proc: dict[str, str] = {}
    root_entries: list[LedgerEntry] = []
    processes: list[str] = []
    workflow_lines: list[str] = [
        "workflow {",
        "    ch_input = Channel.fromPath(params.input)",
    ]

    for i, entry in enumerate(tool_entries):
        proc = _proc_name(entry, i)
        entry_to_proc[entry.id] = proc
        processes.append(_make_nf_process(proc, entry))

        # Wire: if parent is in the subset, chain; otherwise treat as root
        if entry.parent_id and entry.parent_id in entry_to_proc:
            parent_proc = entry_to_proc[entry.parent_id]
            workflow_lines.append(f"    {proc}({parent_proc}.out)")
        else:
            root_entries.append(entry)
            workflow_lines.append(f"    {proc}(ch_input)")

    workflow_lines.append("}")

    # Warn about disconnected subgraphs
    header_comments: list[str] = []
    if len(root_entries) > 1:
        root_names = [entry_to_proc[e.id] for e in root_entries]
        logger.warning(
            "Selected entries form %d disconnected subgraphs (roots: %s). "
            "The generated workflow may not represent a single linear pipeline.",
            len(root_entries),
            root_names,
        )
        header_comments.append(
            f"// WARNING: {len(root_entries)} disconnected subgraphs detected.\n"
            f"// Roots: {', '.join(root_names)}\n"
            f"// This may indicate a non-contiguous selection of entries.\n"
        )

    return "\n".join(header_comments + processes) + "\n\n" + "\n".join(workflow_lines)


def to_galaxy_workflow(session: LedgerSession) -> dict:
    """Convert a ledger session into a DAG-aware Galaxy .ga workflow JSON."""
    children, by_id = _build_dag(session)
    ordered = _topological_order(children)

    entry_to_step: dict[str, int] = {}
    steps = {}

    for i, entry in enumerate(ordered):
        entry_to_step[entry.id] = i
        tool_id = entry.tool_spec_name or (
            entry.container.image.split("/")[-1].split(":")[0]
            if entry.container
            else "unknown"
        )
        tool_version = (
            entry.container.image.split(":")[-1]
            if entry.container and ":" in entry.container.image
            else "latest"
        )

        # Build input connections from parent_id
        input_connections = {}
        if entry.parent_id and entry.parent_id in entry_to_step:
            parent_step = entry_to_step[entry.parent_id]
            input_connections["input"] = {"id": parent_step, "output_name": "output"}

        steps[str(i)] = {
            "id": i,
            "type": "tool",
            "tool_id": tool_id,
            "tool_version": tool_version,
            "input_connections": input_connections,
            "position": {"left": 200 * i, "top": 200},
        }

    return {
        "a_galaxy_workflow": "true",
        "format-version": "0.1",
        "name": f"BioLedger Session {session.id}",
        "steps": steps,
    }
