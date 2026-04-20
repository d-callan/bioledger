from __future__ import annotations

from bioledger.forges.analysisforge.crystallize import (
    to_galaxy_workflow,
    to_nextflow,
    to_nextflow_from_entries,
)
from bioledger.ledger.models import (
    ContainerInfo,
    EntryKind,
    LedgerEntry,
    LedgerSession,
)


def _make_entry(
    kind: EntryKind = EntryKind.TOOL_RUN,
    tool_name: str = "fastqc",
    image: str = "quay.io/biocontainers/fastqc:0.11.9--0",
    command: list[str] | None = None,
    parent_id: str | None = None,
) -> LedgerEntry:
    return LedgerEntry(
        kind=kind,
        tool_spec_name=tool_name,
        container=ContainerInfo(
            image=image,
            command=command or ["fastqc", "reads.fastq"],
        ),
        parent_id=parent_id,
        exit_code=0,
    )


def test_to_nextflow_empty_session():
    session = LedgerSession(name="Empty")
    result = to_nextflow(session)
    assert "Empty workflow" in result


def test_to_nextflow_single_entry():
    session = LedgerSession(name="Single")
    entry = _make_entry()
    session.add(entry)
    result = to_nextflow(session)
    assert "process step_0_fastqc" in result
    assert "workflow {" in result
    assert "container" in result


def test_to_nextflow_chained_entries():
    session = LedgerSession(name="Chain")
    e1 = _make_entry(tool_name="fastqc")
    session.add(e1)
    e2 = _make_entry(tool_name="trimmomatic", parent_id=e1.id)
    session.add(e2)
    e3 = _make_entry(tool_name="hisat2", parent_id=e2.id)
    session.add(e3)

    result = to_nextflow(session)
    assert "step_0_fastqc" in result
    assert "step_1_trimmomatic" in result
    assert "step_2_hisat2" in result
    # Check chaining
    assert "step_1_trimmomatic(step_0_fastqc.out)" in result
    assert "step_2_hisat2(step_1_trimmomatic.out)" in result


def test_to_nextflow_skips_non_tool_entries():
    session = LedgerSession(name="Mixed")
    session.add(LedgerEntry(kind=EntryKind.DATA_IMPORT))
    session.add(_make_entry(tool_name="fastqc"))
    result = to_nextflow(session)
    # Only tool_run should produce a process
    assert result.count("process ") == 1


def test_to_nextflow_from_entries_subset():
    e1 = _make_entry(tool_name="fastqc")
    e2 = _make_entry(tool_name="hisat2", parent_id=e1.id)
    result = to_nextflow_from_entries([e1, e2])
    assert "step_0_fastqc" in result
    assert "step_1_hisat2" in result


def test_to_nextflow_from_entries_empty():
    result = to_nextflow_from_entries([])
    assert "Empty workflow" in result


def test_to_nextflow_from_entries_independent_roots():
    """Multiple independent roots represent parallel branches — valid, not a warning."""
    e1 = _make_entry(tool_name="fastqc")
    e2 = _make_entry(tool_name="hisat2")  # no parent — second root
    result = to_nextflow_from_entries([e1, e2])
    assert "process step_0_fastqc" in result
    assert "process step_1_hisat2" in result
    # Neither process should chain to the other
    assert "step_0_fastqc.out" not in result
    assert "step_1_hisat2.out" not in result
    # No bogus warning about parallel independent runs
    assert "WARNING" not in result


def test_to_galaxy_workflow_empty():
    session = LedgerSession(name="Empty")
    result = to_galaxy_workflow(session)
    assert result["a_galaxy_workflow"] == "true"
    assert result["steps"] == {}


def test_to_galaxy_workflow_chained():
    session = LedgerSession(name="Galaxy")
    e1 = _make_entry(tool_name="fastqc")
    session.add(e1)
    e2 = _make_entry(tool_name="hisat2", parent_id=e1.id)
    session.add(e2)

    result = to_galaxy_workflow(session)
    assert len(result["steps"]) == 2
    step_1 = result["steps"]["1"]
    assert step_1["tool_id"] == "hisat2"
    assert step_1["input_connections"]["input"]["id"] == 0
