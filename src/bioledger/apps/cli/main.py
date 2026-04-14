from __future__ import annotations

import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # Load .env into process environment before anything else

import typer  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.table import Table  # noqa: E402

from bioledger.ledger.models import LedgerSession  # noqa: E402
from bioledger.ledger.store import LedgerStore  # noqa: E402

app = typer.Typer(name="bioledger", help="BioLedger: reproducible bio-analysis")
session_app = typer.Typer(help="Manage analysis sessions")
tool_app = typer.Typer(help="Manage tool specifications")
app.add_typer(session_app, name="session")
app.add_typer(tool_app, name="tool")
console = Console()


# --- Session management ---


@session_app.command("new")
def session_new(
    name: str = typer.Option("", help="Session name"),
    description: str = typer.Option("", help="What this analysis is about"),
) -> None:
    """Create a new analysis session."""
    session = LedgerSession(name=name, description=description)
    store = LedgerStore()
    store.create_session(session)
    console.print(f"[green]Session {session.id} created[/green]")
    if name:
        console.print(f"  Name: {name}")


@session_app.command("list")
def session_list(
    all_sessions: bool = typer.Option(
        False, "--all", help="Include archived sessions"
    ),
) -> None:
    """List analysis sessions."""
    store = LedgerStore()
    status = None if all_sessions else "active"
    rows = store.list_sessions(status=status)
    if not rows:
        console.print("[dim]No sessions found.[/dim]")
        return
    table = Table(title="Sessions")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Entries", justify="right")
    table.add_column("Messages", justify="right")
    table.add_column("Updated")
    for r in rows:
        s = store.load_session(r["id"], include_messages=False)
        msg_count = store.message_count(r["id"])
        table.add_row(
            r["id"],
            r["name"] or "(unnamed)",
            r["status"],
            str(len(s.entries)),
            str(msg_count),
            r["updated"][:16],
        )
    console.print(table)


@session_app.command("show")
def session_show(session_id: str) -> None:
    """Show session details, entries, and recent chat."""
    store = LedgerStore()
    s = store.load_session(session_id)
    console.print(f"[bold]Session {s.id}[/bold]  {s.name or '(unnamed)'}")
    console.print(
        f"  Status: {s.status.value}  |  "
        f"Created: {s.created}  |  Updated: {s.updated}"
    )
    if s.description:
        console.print(f"  Description: {s.description}")
    console.print(
        f"  Entries: {len(s.entries)}  |  "
        f"Chat messages: {len(s.chat_messages)}"
    )
    # Show last 5 chat messages
    if s.chat_messages:
        console.print("\n[bold]Recent chat:[/bold]")
        for msg in s.chat_messages[-5:]:
            role_color = "green" if msg.role == "user" else "blue"
            console.print(
                f"  [{role_color}]{msg.role}[/{role_color}]: "
                f"{msg.content[:120]}"
            )


@session_app.command("rename")
def session_rename(session_id: str, name: str) -> None:
    """Rename a session."""
    store = LedgerStore()
    store.rename_session(session_id, name)
    console.print(f"[green]Session {session_id} renamed to '{name}'[/green]")


@session_app.command("describe")
def session_describe(session_id: str, description: str) -> None:
    """Update a session's description."""
    store = LedgerStore()
    store.update_session_description(session_id, description)
    console.print("[green]Description updated[/green]")


@session_app.command("archive")
def session_archive(session_id: str) -> None:
    """Archive a session (soft-delete, still queryable)."""
    store = LedgerStore()
    store.archive_session(session_id)
    console.print(f"[yellow]Session {session_id} archived[/yellow]")


# --- Tool management ---


@tool_app.command("import")
def tool_import(
    path: Path,
    name: str = typer.Option("", help="Override tool name"),
) -> None:
    """Import a tool from Galaxy XML, Nextflow module, or BioLedger YAML."""
    from bioledger.toolspec.load import load_spec
    from bioledger.toolspec.models import ToolSpec
    from bioledger.toolspec.store import ToolStore
    from bioledger.toolspec.validate import validate_spec

    suffix = path.suffix.lower()
    if suffix in (".xml",):
        from bioledger.forges.toolforge.translators.galaxy import from_galaxy_xml

        exec_spec = from_galaxy_xml(path.read_text())
        if name:
            exec_spec.name = name
        spec = ToolSpec(execution=exec_spec)
    elif suffix in (".nf",):
        from bioledger.forges.toolforge.translators.nextflow import (
            from_nextflow_module,
        )

        exec_spec = from_nextflow_module(path.read_text())
        if name:
            exec_spec.name = name
        spec = ToolSpec(execution=exec_spec)
    elif suffix in (".yaml", ".yml"):
        spec = load_spec(path)
    else:
        console.print(f"[red]Unsupported file type: {suffix}[/red]")
        raise typer.Exit(1)

    result = validate_spec(spec)
    store = ToolStore()
    out = store.save(spec)
    console.print(f"[green]Imported '{spec.name}' → {out}[/green]")

    if result.issues:
        for issue in result.issues:
            color = (
                "red" if issue.severity.value == "error"
                else "yellow" if issue.severity.value == "warning"
                else "dim"
            )
            console.print(f"  [{color}]{issue.severity.value}[/{color}] {issue.message}")


@tool_app.command("validate")
def tool_validate(
    path: Path,
    strict: bool = typer.Option(False, "--strict", help="Treat warnings as errors"),
) -> None:
    """Validate a tool spec file."""
    from bioledger.toolspec.load import load_spec
    from bioledger.toolspec.validate import validate_spec

    spec = load_spec(path)
    result = validate_spec(spec, strict=strict)

    if result.is_valid and (not strict or result.is_strict_valid):
        console.print(f"[green]✓ {spec.name} is valid[/green]")
    else:
        console.print(f"[red]✗ {spec.name} has issues[/red]")

    for issue in result.issues:
        color = (
            "red" if issue.severity.value == "error"
            else "yellow" if issue.severity.value == "warning"
            else "dim"
        )
        console.print(f"  [{color}]{issue.severity.value}[/{color}] {issue.field}: {issue.message}")

    if not result.is_valid:
        raise typer.Exit(1)


@tool_app.command("list")
def tool_list(
    search: str = typer.Option("", help="Filter by name substring"),
) -> None:
    """List tool specs in the local store."""
    from bioledger.toolspec.store import ToolStore

    store = ToolStore()
    specs = store.search(name=search) if search else store.list_all()

    if not specs:
        console.print("[dim]No tools found.[/dim]")
        return

    table = Table(title="Tool Specs")
    table.add_column("Name", style="cyan")
    table.add_column("Container")
    table.add_column("Status")
    table.add_column("Inputs", justify="right")
    table.add_column("Outputs", justify="right")

    for spec in specs:
        ex = spec.execution
        table.add_row(
            ex.name,
            ex.container,
            ex.status.value,
            str(len(ex.inputs)),
            str(len(ex.outputs)),
        )
    console.print(table)


@tool_app.command("show")
def tool_show(name: str) -> None:
    """Show details of a tool spec."""
    from bioledger.toolspec.store import ToolStore

    store = ToolStore()
    try:
        spec = store.load(name)
    except KeyError:
        console.print(f"[red]Tool '{name}' not found[/red]")
        raise typer.Exit(1)

    ex = spec.execution
    console.print(f"[bold]{ex.name}[/bold]  v{ex.version or '(unset)'}")
    console.print(f"  Container: {ex.container}")
    console.print(f"  Status:    {ex.status.value}")
    console.print(f"  Command:   {ex.command}")

    if ex.description:
        console.print(f"  Desc:      {ex.description}")

    if ex.inputs:
        console.print("\n  [bold]Inputs:[/bold]")
        for k, v in ex.inputs.items():
            console.print(f"    {k}: {v.format} ({'required' if v.required else 'optional'})")

    if ex.outputs:
        console.print("\n  [bold]Outputs:[/bold]")
        for k, v in ex.outputs.items():
            console.print(f"    {k}: {v.format}")

    if ex.parameters:
        console.print("\n  [bold]Parameters:[/bold]")
        for k, v in ex.parameters.items():
            default = f" = {v.default}" if v.default is not None else ""
            console.print(f"    {k}: {v.type.value}{default}")


@tool_app.command("export")
def tool_export(
    name: str,
    format: str = typer.Option("nextflow", help="Export format: 'nextflow' or 'galaxy'"),
    output: Path = typer.Option(None, "-o", help="Output file (default: stdout)"),
) -> None:
    """Export a tool spec to Galaxy XML or Nextflow DSL2."""
    from bioledger.toolspec.store import ToolStore

    store = ToolStore()
    try:
        spec = store.load(name)
    except KeyError:
        console.print(f"[red]Tool '{name}' not found[/red]")
        raise typer.Exit(1)

    if format == "galaxy":
        from bioledger.forges.toolforge.translators.galaxy import to_galaxy_xml
        result = to_galaxy_xml(spec.execution)
    elif format == "nextflow":
        from bioledger.forges.toolforge.translators.nextflow import to_nextflow_process
        result = to_nextflow_process(spec.execution)
    else:
        console.print(f"[red]Unknown format: {format}[/red]")
        raise typer.Exit(1)

    if output:
        output.write_text(result)
        console.print(f"[green]Written to {output}[/green]")
    else:
        console.print(result)


# --- Analysis ---


@app.command()
def resume(session_id: str) -> None:
    """Resume an interactive analysis session (chat mode)."""
    asyncio.run(_analysis_chat(session_id))


async def _analysis_chat(session_id: str) -> None:
    """Interactive chat loop for AnalysisForge.

    Handles: dataset loading, LLM-powered tool suggestions, tool execution with
    user confirmation, entry review, and selective RO-Crate packaging.
    """
    from bioledger.config import BioLedgerConfig
    from bioledger.core.llm.agents import ForgeDeps
    from bioledger.forges.analysisforge.agent import (
        AnalysisForgeAgent,
        ChatIntent,
    )
    from bioledger.forges.isaforge.dataset import load_dataset_from_isatab
    from bioledger.ledger.models import EntryKind

    config = BioLedgerConfig()
    store = LedgerStore()
    session = store.load_session(session_id, include_messages=True)
    agent = AnalysisForgeAgent(config, session, store)

    # Restore dataset from prior DATA_IMPORT entry (if any)
    for entry in session.entries:
        if entry.kind == EntryKind.DATA_IMPORT and "source" in entry.params:
            source = entry.params["source"]
            # Strip conversion suffix if present (e.g. "path (converted to ISA-Tab at ...)")
            if " (converted to ISA-Tab at " in source:
                isatab_path = source.split("(converted to ISA-Tab at ")[-1].rstrip(")")
            else:
                isatab_path = source
            try:
                dataset = load_dataset_from_isatab(Path(isatab_path), validate=False)
                agent.dataset = dataset
            except Exception:
                pass  # dataset dir may have moved; user can re-load

    console.print(f"\n[bold]Session: {session.name or session.id}[/bold]")
    console.print(
        f"  {len(session.entries)} entries, "
        f"{len(session.chat_messages)} messages"
    )
    console.print(
        "[dim]Type 'quit' to exit, 'review' to see entries, "
        "'package' to build RO-Crate[/dim]\n"
    )

    deps = ForgeDeps(
        config=config,
        session=session,
        store=store,
        context_mode="chat",
    )

    while True:
        try:
            user_input = console.input("[green]you>[/green] ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue
        if user_input.lower() == "quit":
            break

        # Record user message
        session.add_message("user", user_input, forge="analysisforge")
        store.append_message(session.id, session.chat_messages[-1])

        # --- Special commands ---

        if user_input.lower() == "review":
            entries = agent.review_entries()
            for e in entries:
                kind = e["kind"]
                icon = (
                    "[yellow]TOOL[/yellow]"
                    if kind == "tool_run"
                    else "[cyan]DATA[/cyan]"
                    if kind == "data_import"
                    else "[dim]NOTE[/dim]"
                )
                console.print(
                    f"  {icon} [{e['id']}] {e['kind']}: "
                    f"{e['tool'] or e['notes']}  "
                    f"outputs={[Path(p).name for p in e['outputs']]}"
                )
            continue

        if user_input.lower().startswith("package"):
            console.print("\n[bold]Package session into RO-Crate[/bold]")
            entries = agent.review_entries()

            console.print(
                "Select entries to include (comma-separated IDs, or 'all'):"
            )
            for e in entries:
                if e["kind"] in ("tool_run", "script_run"):
                    console.print(
                        f"  [{e['id']}] {e['tool']} -> "
                        f"{[Path(p).name for p in e['outputs']]}"
                    )

            selection = console.input("[green]entries>[/green] ").strip()

            if selection.lower() == "all":
                entry_ids = None
            else:
                entry_ids = [eid.strip() for eid in selection.split(",")]

            from bioledger.forges.crateforge.builder import build_rocrate

            output_dir = config.home_dir / "crates" / session.id
            crate_dir = build_rocrate(session, output_dir, entry_ids=entry_ids)
            console.print(f"[green]RO-Crate written to {crate_dir}[/green]")

            response = (
                f"Packaged {'selected entries' if entry_ids else 'all entries'} "
                f"into RO-Crate at {crate_dir}"
            )
            session.add_message("assistant", response, forge="analysisforge")
            store.append_message(session.id, session.chat_messages[-1])
            continue

        if user_input.lower().startswith("load "):
            data_path = Path(user_input.split(" ", 1)[1].strip())
            try:
                dataset = await agent.load_dataset(data_path)

                # Show dataset summary
                samples = len(dataset.sample_metadata)
                orgs = ", ".join(dataset.organisms) if dataset.organisms else "unknown"
                fmts = ", ".join(dataset.file_formats) if dataset.file_formats else "none"
                console.print(
                    f'\n[green]Loaded dataset "{dataset.name}"[/green]'
                    f"\n  Samples: {samples}"
                    f"\n  Organisms: {orgs}"
                    f"\n  File formats: {fmts}"
                    f"\n  Files: {len(dataset.files)}"
                )

                # Check for remote files
                remote = dataset.remote_files()
                if remote:
                    console.print(
                        f"\n[yellow]Found {len(remote)} remote files:[/yellow]"
                    )
                    for f in remote:
                        console.print(f"  - {f.location}")
                    if typer.confirm("Download these files?"):
                        download_dir = (
                            config.home_dir / "datasets" / dataset.name
                        )
                        await agent.download_remote(download_dir)
                        console.print(
                            f"[green]Downloaded to {download_dir}[/green]"
                        )

                # Suggest workflow
                suggestions = await agent.suggest_workflow()
                response = suggestions["prompt_for_user"]
                console.print(f"\n[blue]assistant>[/blue] {response}")

                if suggestions.get("workflow"):
                    console.print("\n[bold]Suggested workflow:[/bold]")
                    for i, step in enumerate(suggestions["workflow"], 1):
                        tools = suggestions.get("tools_by_step", {}).get(
                            step, []
                        )
                        tools_str = f" ({', '.join(tools)})" if tools else ""
                        console.print(f"  {i}. {step}{tools_str}")

            except Exception as e:
                response = f"Failed to load dataset: {e}"
                console.print(f"[red]{response}[/red]")

            session.add_message("assistant", response, forge="analysisforge")
            store.append_message(session.id, session.chat_messages[-1])
            continue

        # --- General conversation: LLM decides what to do ---

        result = await agent._chat_agent.run(
            user_input, deps=deps, message_history=deps.message_history()
        )
        chat_response = result.output
        response = chat_response.message

        if chat_response.intent == ChatIntent.SUGGEST_TOOL:
            try:
                tool_request = await agent.suggest_next_tool(user_input)
                console.print(
                    f"\n[yellow]Suggested: {tool_request.tool_name}[/yellow]"
                    f"\n  Reason: {tool_request.rationale}"
                    f"\n  Params: {tool_request.params_as_dict()}"
                )

                if typer.confirm("Run this tool?"):
                    input_files, parent_id = _resolve_inputs(
                        agent, tool_request, user_input
                    )
                    from uuid import uuid4

                    run_id = uuid4().hex[:8]
                    output_dir = (
                        config.home_dir
                        / "outputs"
                        / session.id
                        / f"{tool_request.tool_name}_{run_id}"
                    )

                    entry, run_result = await agent.run_tool_with_logging(
                        tool_request.tool_name,
                        input_files,
                        output_dir,
                        params=tool_request.params_as_dict(),
                        parent_id=parent_id,
                    )

                    if run_result.exit_code == 0:
                        outputs = [
                            Path(f.path).name
                            for f in entry.files
                            if f.role == "output"
                        ]
                        # Read small output files so the LLM can discuss results
                        output_snippets = []
                        for f in entry.files:
                            if f.role == "output":
                                op = Path(f.path)
                                if op.exists() and op.stat().st_size < 10_000:
                                    try:
                                        output_snippets.append(
                                            f"--- {op.name} ---\n{op.read_text()}"
                                        )
                                    except Exception:
                                        pass
                        response = (
                            f"{tool_request.tool_name} completed. "
                            f"Outputs: {outputs}"
                        )
                        if output_snippets:
                            response += "\n" + "\n".join(output_snippets)
                    else:
                        response = (
                            f"{tool_request.tool_name} failed "
                            f"(exit {run_result.exit_code}): "
                            f"{run_result.stderr[:200]}"
                        )

                    console.print(f"\n[blue]assistant>[/blue] {response}")
                else:
                    response = (
                        "OK, skipping tool run. What would you like to do "
                        "instead?"
                    )
                    console.print(f"\n[blue]assistant>[/blue] {response}")
            except KeyError as e:
                response = f"Tool not found in store: {e}"
                console.print(f"[red]{response}[/red]")
            except Exception as e:
                response = f"Error suggesting/running tool: {e}"
                console.print(f"[red]{response}[/red]")
        else:
            # RESPOND or CLARIFY — just show the message
            console.print(f"\n[blue]assistant>[/blue] {response}")

        # Record assistant response
        session.add_message("assistant", response, forge="analysisforge")
        store.append_message(session.id, session.chat_messages[-1])


def _resolve_inputs(
    agent: "AnalysisForgeAgent",  # noqa: F821
    tool_request: "ToolRunRequest",  # noqa: F821
    user_input: str = "",
) -> tuple[dict[str, Path], str | None]:
    """Resolve input file paths from tool request mapping.

    Resolution order for each input_name -> source:
      1. Literal file path (if exists on disk)
      2. Match against prior session output files (by filename or substring)
      3. Match against dataset files (by filename, format, or substring)
      4. Search ISA-Tab directory for structural files

    Returns:
        (input_files, parent_id) — parent_id is set only when an input
        was resolved from a prior tool run's output (real data dependency).

    Raises ValueError if any required input cannot be resolved.
    """
    from bioledger.ledger.models import EntryKind

    input_files: dict[str, Path] = {}
    parent_id: str | None = None
    mapping = tool_request.mapping_as_dict()

    for input_name, source in mapping.items():
        resolved = None

        # 1. Literal path
        p = Path(source)
        if p.exists():
            resolved = p

        # 2. Search prior session outputs (most recent first)
        if resolved is None:
            for entry in reversed(agent.session.entries):
                if entry.kind in (EntryKind.TOOL_RUN, EntryKind.SCRIPT_RUN):
                    for f in entry.files:
                        if f.role == "output":
                            fp = Path(f.path)
                            if fp.name == source or source in str(fp):
                                resolved = fp
                                parent_id = entry.id
                                break
                if resolved:
                    break

        # 3. Search dataset files (assay data files)
        if resolved is None and agent.dataset:
            for f in agent.dataset.files:
                loc = f.downloaded_path or f.location
                lp = Path(loc)
                if lp.name == source or source in str(lp) or f.format == source:
                    if lp.exists():
                        resolved = lp
                        break

        # 4. Search ISA-Tab directory for structural files
        #    (s_study.txt, a_assay.txt, i_investigation.txt, etc.)
        if resolved is None and agent.dataset and agent.dataset.isa_tab_dir:
            candidate = agent.dataset.isa_tab_dir / source
            if candidate.exists():
                resolved = candidate

        if resolved is None:
            raise ValueError(
                f"Cannot resolve input '{input_name}' from source '{source}'. "
                f"Provide an explicit file path, a filename from a prior tool "
                f"output, or a filename/format from the loaded dataset."
            )
        input_files[input_name] = resolved

    return input_files, parent_id


# --- Crystallize ---


@app.command()
def crystallize(
    session_id: str,
    format: str = typer.Option(
        "nextflow", help="Workflow format: 'nextflow' or 'galaxy'"
    ),
    entry_ids: list[str] = typer.Option(
        None, "--entry", "-e", help="Specific entry IDs to include (default: all)"
    ),
) -> None:
    """Convert a session (or selected entries) into a reproducible workflow."""
    store = LedgerStore()
    session = store.load_session(session_id)

    if entry_ids:
        from bioledger.forges.analysisforge.crystallize import (
            to_nextflow_from_entries,
        )

        entries = [e for e in session.entries if e.id in set(entry_ids)]
        console.print(to_nextflow_from_entries(entries))
    elif format == "nextflow":
        from bioledger.forges.analysisforge.crystallize import to_nextflow

        console.print(to_nextflow(session))
    elif format == "galaxy":
        from bioledger.forges.analysisforge.crystallize import to_galaxy_workflow

        console.print(json.dumps(to_galaxy_workflow(session), indent=2))


# --- Package ---


@app.command()
def package(
    session_id: str,
    entry_ids: list[str] = typer.Option(
        None, "--entry", "-e", help="Specific entry IDs (default: all)"
    ),
    output_dir: Path = typer.Option(
        None, help="Output directory (default: ~/.bioledger/crates/<session_id>)"
    ),
) -> None:
    """Package a session (or selected entries) into an RO-Crate."""
    from bioledger.config import BioLedgerConfig
    from bioledger.forges.crateforge.builder import build_rocrate

    config = BioLedgerConfig()
    store = LedgerStore()
    session = store.load_session(session_id)

    if output_dir is None:
        output_dir = config.home_dir / "crates" / session_id

    crate_dir = build_rocrate(session, output_dir, entry_ids=entry_ids)
    console.print(f"[green]RO-Crate written to {crate_dir}[/green]")
    console.print(
        f"  Entries: {len(entry_ids) if entry_ids else len(session.entries)}"
    )
    console.print("  Includes: workflow.nf, data files, ledger.json")


if __name__ == "__main__":
    app()
