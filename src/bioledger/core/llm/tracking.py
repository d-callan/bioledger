from __future__ import annotations

from pydantic_ai.agent import AgentRunResult

from bioledger.ledger.models import EntryKind, LedgerEntry, LedgerSession, LLMCallInfo


def log_llm_result(
    session: LedgerSession, result: AgentRunResult, parent_id: str | None = None
) -> LedgerEntry:
    """Extract message history from a pydantic-ai run and log it."""
    messages = result.all_messages()
    tool_calls = [
        part.tool_name
        for msg in messages
        if hasattr(msg, "parts")
        for part in msg.parts
        if hasattr(part, "tool_name")
    ]

    entry = LedgerEntry(
        kind=EntryKind.LLM_CALL,
        parent_id=parent_id,
        llm_call=LLMCallInfo(
            model=str(getattr(result, "_model_name", "unknown")),
            prompt_summary=str(messages[0])[:200] if messages else "",
            full_messages=[m.model_dump() for m in messages],
            output_summary=str(result.output)[:500],
            tokens_used=sum(
                getattr(m, "usage", None).input_tokens
                + getattr(m, "usage", None).output_tokens
                for m in messages
                if getattr(m, "usage", None)
            )
            if messages
            else 0,
            tool_calls=tool_calls,
        ),
    )
    session.add(entry)
    return entry
