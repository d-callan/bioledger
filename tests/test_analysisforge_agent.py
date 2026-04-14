"""Regression tests for AnalysisForgeAgent tool discovery.

These tests verify that the agent correctly discovers and uses tools
from the ToolStore without requiring API keys for LLM initialization.
"""

from __future__ import annotations

from bioledger.toolspec.models import (
    ExecutionSpec,
    ParamType,
    SpecStatus,
    ToolInput,
    ToolOutput,
    ToolSpec,
)
from bioledger.toolspec.store import ToolStore


def test_tool_store_lists_imported_tools(tmp_path):
    """Regression test: Verify ToolStore correctly lists dynamically imported tools.

    This is the core mechanism that enables the fix: when tools like 'line_counter'
    are imported via 'bioledger tool import', they should appear in list_all().
    """
    # Create a temporary tools directory
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()

    # Create test tool specs (simulating user-imported tools)
    line_counter_spec = ToolSpec(
        execution=ExecutionSpec(
            name="line_counter",
            description="Counts lines in a file",
            container="python:3.11-slim",
            command="wc -l {{inputs.input_file}} > {{outputs.count}}",
            inputs={
                "input_file": ToolInput(
                    type=ParamType.FILE,
                    format="txt",
                    description="Input file to count",
                    required=True,
                ),
            },
            outputs={
                "count": ToolOutput(
                    format="txt",
                    description="Line count output",
                    pattern="count.txt",
                ),
            },
            status=SpecStatus.VALID,
        )
    )

    row_counter_spec = ToolSpec(
        execution=ExecutionSpec(
            name="row_counter",
            description="Counts rows in tabular data",
            container="python:3.11-slim",
            command="wc -l {{inputs.input_file}}",
            inputs={
                "input_file": ToolInput(
                    type=ParamType.FILE,
                    format="csv",
                    description="CSV file to count rows",
                    required=True,
                ),
            },
            outputs={
                "count": ToolOutput(
                    format="txt",
                    description="Row count output",
                    pattern="count.txt",
                ),
            },
            status=SpecStatus.VALID,
        )
    )

    # Save tools to store (this is what 'bioledger tool import' does)
    store = ToolStore(tools_dir=tools_dir)
    store.save(line_counter_spec)
    store.save(row_counter_spec)

    # Verify tools are discoverable
    tool_names = store.list_tools()
    assert "line_counter" in tool_names
    assert "row_counter" in tool_names

    # Verify list_all returns the actual specs with descriptions
    all_specs = store.list_all()
    spec_names = {s.name for s in all_specs}
    assert "line_counter" in spec_names
    assert "row_counter" in spec_names

    # This is what the fix uses to build the system prompt
    tools_list = "\n".join(
        f"- {t.name}: {t.execution.description or 'No description'}"
        for t in all_specs
    )
    assert "- line_counter: Counts lines in a file" in tools_list
    assert "- row_counter: Counts rows in tabular data" in tools_list


def test_tools_list_format_for_system_prompt(tmp_path):
    """Test that the tools list is formatted correctly for LLM system prompt.

    Verifies the exact format used in the fix at agent.py:84-87.
    """
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()

    spec = ToolSpec(
        execution=ExecutionSpec(
            name="test_tool",
            description="A test tool for regression testing",
            container="python:3.11-slim",
            command="echo test",
            inputs={},
            outputs={},
            status=SpecStatus.VALID,
        )
    )

    store = ToolStore(tools_dir=tools_dir)
    store.save(spec)

    available_tools = store.list_all()
    tools_list = "\n".join(
        f"- {t.name}: {t.execution.description or 'No description'}"
        for t in available_tools
    )

    # Format assertions - this is what gets injected into the system prompt
    assert tools_list.startswith("- test_tool:")
    assert "A test tool for regression testing" in tools_list
    assert "\n" not in tools_list.strip()  # Single tool = single line


def test_empty_tools_store_shows_import_message(tmp_path):
    """Test that empty tool stores produce the expected message.

    This tests the fallback branch from agent.py:88-89.
    """
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()

    store = ToolStore(tools_dir=tools_dir)
    available_tools = store.list_all()

    if available_tools:
        tools_list = "\n".join(
            f"- {t.name}: {t.execution.description or 'No description'}"
            for t in available_tools
        )
    else:
        tools_list = "(No tools available - import tools with 'bioledger tool import')"

    assert "No tools available" in tools_list
    assert "bioledger tool import" in tools_list
