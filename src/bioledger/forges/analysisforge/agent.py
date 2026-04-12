from __future__ import annotations

import hashlib
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from bioledger.config import BioLedgerConfig
from bioledger.core.llm.agents import ForgeDeps, make_agent
from bioledger.forges.analysisforge.executor import run_tool
from bioledger.forges.analysisforge.suggest import suggest_analysis_for_dataset
from bioledger.forges.isaforge.builder import csv_to_isatab
from bioledger.forges.isaforge.dataset import (
    DataSet,
    load_dataset_from_isatab,
)
from bioledger.forges.isaforge.download import download_remote_files
from bioledger.ledger.models import EntryKind, FileRef, LedgerEntry, LedgerSession
from bioledger.ledger.store import LedgerStore
from bioledger.toolspec.store import ToolStore


class ToolRunRequest(BaseModel):
    """LLM-structured request to run a tool."""

    tool_name: str
    rationale: str  # why this tool for this step
    suggested_params: dict[str, Any] = {}
    input_mapping: dict[str, str] = {}  # tool_input_name → file path or prior output ref


class ChatIntent(str, Enum):
    """What the LLM wants to do in response to the user's message."""

    RESPOND = "respond"  # pure conversational reply, no action
    SUGGEST_TOOL = "suggest_tool"  # LLM thinks a tool should be run next
    CLARIFY = "clarify"  # LLM needs more info before acting


class ChatResponse(BaseModel):
    """Structured output from the conversational chat agent.
    The intent field replaces fragile keyword scanning of free text."""

    intent: ChatIntent
    message: str  # the text shown to the user
    suggested_tool: str | None = None  # tool name, only when intent == SUGGEST_TOOL


class AnalysisForgeAgent:
    """Orchestrates the full interactive analysis session.

    Responsibilities:
    - Load ISA-Tab datasets (records DATA_IMPORT entry)
    - Suggest workflows and tools via LLM
    - Run tools with user confirmation (records TOOL_RUN entries)
    - Log all LLM interactions (records LLM_CALL entries + ChatMessages)
    - Provide entry review for selective RO-Crate packaging

    Design note — planned decomposition:
      This class currently handles dataset loading, tool suggestion, tool execution,
      and chat orchestration. Future refactoring should extract:
        1. DatasetManager — load_dataset, download handling, format detection
        2. ToolRunner — run_tool_with_logging, _resolve_inputs, _hash_file
        3. ChatOrchestrator — _analysis_chat loop, message recording
        4. AnalysisForgeAgent — thin coordinator delegating to the above
      This keeps each concern testable in isolation and reduces class size.
      The Forge base class (core/forge.py) provides the lifecycle contract.
    """

    def __init__(
        self, config: BioLedgerConfig, session: LedgerSession, store: LedgerStore
    ):
        self.config = config
        self.session = session
        self.store = store
        self.tool_store = ToolStore()
        self.dataset: DataSet | None = None

        # Main conversational agent — structured output with explicit intent
        self._chat_agent = make_agent(
            config,
            task="chat",
            instructions=(
                "You are AnalysisForge, a bioinformatics analysis assistant. "
                "You help researchers analyze their data step by step. "
                "You can load ISA-Tab datasets, suggest analysis workflows, "
                "run bioinformatics tools, and package results into "
                "reproducible RO-Crates.\n\n"
                "When the user loads a dataset, summarize what you see and "
                "suggest a workflow. Always confirm tool runs before executing. "
                "After each tool run, report results and suggest next steps. "
                "When the user wants to package results, help them review and "
                "select entries.\n\n"
                "IMPORTANT: Set intent='suggest_tool' and suggested_tool=<name> "
                "ONLY when you believe a specific tool should be executed next. "
                "Use intent='respond' for all other conversational replies. "
                "Use intent='clarify' when you need more info."
            ),
            output_type=ChatResponse,
        )

        # Tool selection agent — structured output
        self._tool_select_agent = make_agent(
            config,
            task="analysis_suggest",
            instructions=(
                "You are a bioinformatics tool selection expert. Given a "
                "user's goal, the dataset context, and available tools, "
                "suggest which tool to run next with appropriate parameters. "
                "Return a structured ToolRunRequest."
            ),
            output_type=ToolRunRequest,
        )

    async def load_dataset(self, path: Path) -> DataSet:
        """Load a dataset into the session, record as DATA_IMPORT entry.

        Accepts either:
        - A CSV samplesheet file (.csv) — converted to ISA-Tab via ISAForge first
        - An ISA-Tab directory (containing i_investigation.txt)

        AnalysisForge always works with ISA-Tab internally for proper
        provenance and metadata tracking.
        """
        if path.is_file() and path.suffix.lower() == ".csv":
            # Route through ISAForge: CSV → ISA-Tab → load
            isatab_dir = (
                self.config.home_dir / "datasets" / path.stem
            )
            await csv_to_isatab(path, isatab_dir, config=self.config)
            dataset = load_dataset_from_isatab(isatab_dir, validate=False)
            source_desc = f"{path} (converted to ISA-Tab at {isatab_dir})"
        else:
            dataset = load_dataset_from_isatab(path)
            source_desc = str(path)
        self.dataset = dataset

        # Record DATA_IMPORT entry in ledger
        file_refs = []
        for f in dataset.files:
            if not f.is_remote:
                p = Path(f.location)
                if p.exists():
                    sha = hashlib.sha256(p.read_bytes()).hexdigest()
                    file_refs.append(
                        FileRef(
                            path=str(p),
                            sha256=sha,
                            size_bytes=p.stat().st_size,
                            role="input",
                        )
                    )

        entry = LedgerEntry(
            kind=EntryKind.DATA_IMPORT,
            files=file_refs,
            params={
                "source": source_desc,
                "organisms": dataset.organisms,
                "assay_type": dataset.assay_type,
                "file_formats": list(dataset.file_formats),
                "file_count": len(dataset.files),
                "remote_count": len(dataset.remote_files()),
            },
            notes=f"Loaded dataset: {dataset.name}",
        )
        self.session.add(entry)
        self.store.save_session(self.session)

        return dataset

    async def download_remote(self, download_dir: Path) -> DataSet:
        """Download remote files in the dataset (requires prior user confirmation)."""
        if not self.dataset:
            raise ValueError("No dataset loaded")
        self.dataset = await download_remote_files(
            self.dataset,
            download_dir,
            user_confirmed=True,
        )
        return self.dataset

    async def suggest_workflow(self, user_goal: str | None = None) -> dict:
        """Get LLM-powered workflow and tool suggestions for the loaded dataset."""
        if not self.dataset:
            raise ValueError("No dataset loaded — load ISA-Tab first")

        deps = ForgeDeps(
            config=self.config,
            session=self.session,
            store=self.store,
            context_mode="chat",
        )
        return await suggest_analysis_for_dataset(self.dataset, user_goal, deps)

    async def suggest_next_tool(self, user_message: str) -> ToolRunRequest:
        """LLM suggests the next tool to run based on conversation context."""
        deps = ForgeDeps(
            config=self.config,
            session=self.session,
            store=self.store,
            context_mode="chat",
        )

        available_tools = self.tool_store.list_all()
        tools_summary = "\n".join(
            f"- {t.name}: {t.execution.description}" for t in available_tools
        )

        # Recent outputs from last tool run
        last_outputs: list[str] = []
        for entry in reversed(self.session.entries):
            if entry.kind in (EntryKind.TOOL_RUN, EntryKind.SCRIPT_RUN):
                last_outputs = [f.path for f in entry.files if f.role == "output"]
                break

        context = (
            f"User request: {user_message}\n\n"
            f"Dataset: {self.dataset.name if self.dataset else 'none'}\n"
            f"Assay type: {self.dataset.assay_type if self.dataset else 'unknown'}\n"
            f"File formats: "
            f"{', '.join(self.dataset.file_formats) if self.dataset else 'unknown'}\n\n"
            f"Session history ({len(self.session.entries)} entries):\n"
            f"{self._session_summary()}\n\n"
            f"Last outputs: {last_outputs}\n\n"
            f"Available tools:\n{tools_summary}\n"
        )
        result = await self._tool_select_agent.run(context, deps=deps)
        return result.output

    async def run_tool_with_logging(
        self,
        tool_name: str,
        input_files: dict[str, Path],
        output_dir: Path,
        params: dict | None = None,
        parent_id: str | None = None,
    ) -> tuple[LedgerEntry, Any]:
        """Run a tool and log everything to the session."""
        spec = self.tool_store.load(tool_name)

        # Auto-chain: if no parent_id, link to last tool_run entry
        if parent_id is None:
            for entry in reversed(self.session.entries):
                if entry.kind in (EntryKind.TOOL_RUN, EntryKind.SCRIPT_RUN):
                    parent_id = entry.id
                    break

        entry, result = run_tool(
            self.session,
            spec,
            input_files,
            output_dir,
            params=params,
            parent_id=parent_id,
        )
        self.store.save_session(self.session)
        return entry, result

    def review_entries(self) -> list[dict]:
        """Return a summary of all session entries for user review."""
        summaries = []
        for entry in self.session.entries:
            inputs = [f.path for f in entry.files if f.role == "input"]
            outputs = [f.path for f in entry.files if f.role == "output"]
            summaries.append(
                {
                    "id": entry.id,
                    "kind": entry.kind.value,
                    "tool": entry.tool_spec_name or "",
                    "timestamp": entry.timestamp.isoformat(),
                    "inputs": inputs,
                    "outputs": outputs,
                    "params": entry.params,
                    "exit_code": entry.exit_code,
                    "notes": entry.notes,
                    "parent_id": entry.parent_id,
                }
            )
        return summaries

    def _session_summary(self) -> str:
        """One-line-per-entry summary for LLM context."""
        lines = []
        for entry in self.session.entries:
            if entry.kind == EntryKind.TOOL_RUN:
                out_files = [
                    Path(f.path).name for f in entry.files if f.role == "output"
                ]
                lines.append(
                    f"  [{entry.id}] {entry.tool_spec_name} -> "
                    f"{', '.join(out_files)} (exit={entry.exit_code})"
                )
            elif entry.kind == EntryKind.DATA_IMPORT:
                lines.append(f"  [{entry.id}] data_import: {entry.notes}")
        return "\n".join(lines) or "  (no entries yet)"
