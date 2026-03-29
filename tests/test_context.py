from __future__ import annotations

from bioledger.core.llm.context import (
    MAX_CHAT_MESSAGES,
    MAX_MESSAGE_CHARS,
    trim_message_history,
)
from bioledger.ledger.models import ChatMessage


def test_trim_empty():
    result = trim_message_history([])
    assert result == []


def test_trim_under_limit():
    msgs = [ChatMessage(role="user", content=f"msg {i}") for i in range(5)]
    result = trim_message_history(msgs)
    assert len(result) == 5


def test_trim_over_limit():
    msgs = [ChatMessage(role="user", content=f"msg {i}") for i in range(100)]
    result = trim_message_history(msgs, max_messages=10)
    assert len(result) == 10
    # Should keep the most recent
    assert result[-1].content == "msg 99"
    assert result[0].content == "msg 90"


def test_trim_long_messages():
    long_content = "x" * 5000
    msgs = [ChatMessage(role="user", content=long_content)]
    result = trim_message_history(msgs, max_chars=100)
    assert len(result) == 1
    # 100 + "... [truncated]" = 116 chars
    assert len(result[0].content) <= 120


def test_trim_defaults():
    assert MAX_CHAT_MESSAGES == 50
    assert MAX_MESSAGE_CHARS == 2000
