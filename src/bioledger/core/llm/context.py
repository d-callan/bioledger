from __future__ import annotations

from bioledger.ledger.models import ChatMessage

# Context window budget constants
MAX_CHAT_MESSAGES = 50
MAX_MESSAGE_CHARS = 2000


def trim_message_history(
    messages: list[ChatMessage],
    max_messages: int = MAX_CHAT_MESSAGES,
    max_chars: int = MAX_MESSAGE_CHARS,
) -> list[ChatMessage]:
    """Trim chat messages to fit within context budget.

    - Keeps only the last `max_messages` messages.
    - Truncates individual messages longer than `max_chars`.
    """
    trimmed = messages[-max_messages:] if len(messages) > max_messages else list(messages)
    result = []
    for msg in trimmed:
        if len(msg.content) > max_chars:
            truncated = msg.model_copy(
                update={"content": msg.content[:max_chars] + "... [truncated]"}
            )
            result.append(truncated)
        else:
            result.append(msg)
    return result
