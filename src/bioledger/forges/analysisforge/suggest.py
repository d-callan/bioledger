from __future__ import annotations

from pydantic import BaseModel

from bioledger.config import BioLedgerConfig
from bioledger.core.llm.agents import ForgeDeps, make_agent
from bioledger.forges.isaforge.dataset import DataSet
from bioledger.toolspec.store import ToolStore


class WorkflowSuggestion(BaseModel):
    """LLM-generated workflow suggestion for a dataset."""

    analysis_steps: list[str]  # e.g. ["Quality control", "Alignment", "Quantification"]
    rationale: str  # why this workflow makes sense
    user_confirmation_prompt: str  # conversational prompt to confirm/refine
    alternative_approaches: list[str] = []  # other valid workflows user might consider


async def suggest_workflow_for_dataset(
    dataset: DataSet,
    user_goal: str | None = None,
    deps: ForgeDeps | None = None,
) -> WorkflowSuggestion:
    """Use LLM to suggest analysis workflow based on dataset metadata."""
    config = deps.config if deps else BioLedgerConfig()

    formats_str = ", ".join(sorted(dataset.file_formats))
    organisms_str = ", ".join(dataset.organisms) if dataset.organisms else "unknown organism"
    sample_count = len(dataset.sample_metadata)

    context = (
        f"Dataset: {dataset.name}\n"
        f"Description: {dataset.description}\n"
        f"Assay type: {dataset.assay_type}\n"
        f"Organism(s): {organisms_str}\n"
        f"File formats: {formats_str}\n"
        f"Sample count: {sample_count}\n"
    )
    if user_goal:
        context += f"\nUser's stated goal: {user_goal}"

    agent = make_agent(
        config,
        task="analysis_suggest",
        instructions=(
            "You are a bioinformatics workflow expert. Given a dataset's metadata, "
            "suggest a typical analysis workflow as a sequence of steps. "
            "Consider the assay type, organism, and file formats. "
            "Provide a clear rationale and ask the user to confirm or refine the workflow. "
            "Also suggest alternative approaches if relevant."
        ),
        output_type=WorkflowSuggestion,
    )

    prompt = (
        f"Suggest an analysis workflow for this dataset:\n\n{context}\n\n"
        "What are the typical analysis steps, and what should I ask the user to confirm?"
    )
    result = await agent.run(prompt, deps=deps)
    return result.output


async def suggest_tools_for_workflow(
    dataset: DataSet,
    workflow: WorkflowSuggestion,
    deps: ForgeDeps | None = None,
) -> dict[str, list[str]]:
    """Match tools from ToolStore to each workflow step."""
    tool_store = ToolStore()
    config = deps.config if deps else BioLedgerConfig()

    # Get all tools that match dataset formats
    all_matching_tools: set[str] = set()
    for fmt in dataset.file_formats:
        tools = tool_store.search(input_format=fmt)
        all_matching_tools.update(t.name for t in tools)

    tools_by_step: dict[str, list[str]] = {}
    for step in workflow.analysis_steps:
        agent = make_agent(
            config,
            task="analysis_suggest",
            instructions=(
                "You are a bioinformatics tool expert. Given an analysis step "
                "and a list of tools, identify which tools are relevant for "
                "that step. Return only the tool names that match."
            ),
            output_type=list[str],
        )

        tools_list = "\n".join(f"- {t}" for t in sorted(all_matching_tools))
        prompt = (
            f"Analysis step: {step}\n"
            f"Dataset formats: {', '.join(dataset.file_formats)}\n"
            f"Available tools:\n{tools_list}\n\n"
            f"Which tools are relevant for this step? Return only the tool names."
        )

        result = await agent.run(prompt, deps=deps)
        tools_by_step[step] = result.output[:5]

    return tools_by_step


async def suggest_analysis_for_dataset(
    dataset: DataSet,
    user_goal: str | None = None,
    deps: ForgeDeps | None = None,
) -> dict:
    """Full analysis suggestion: workflow + tools + conversational prompt."""
    workflow = await suggest_workflow_for_dataset(dataset, user_goal, deps)
    tools_by_step = await suggest_tools_for_workflow(dataset, workflow, deps)

    return {
        "workflow": workflow.analysis_steps,
        "rationale": workflow.rationale,
        "tools_by_step": tools_by_step,
        "prompt_for_user": workflow.user_confirmation_prompt,
        "alternative_approaches": workflow.alternative_approaches,
        "dataset_summary": {
            "name": dataset.name,
            "formats": list(dataset.file_formats),
            "organisms": dataset.organisms,
            "assay_type": dataset.assay_type,
            "file_count": len(dataset.files),
            "remote_file_count": len(dataset.remote_files()),
        },
    }
