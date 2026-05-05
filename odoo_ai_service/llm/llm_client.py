from __future__ import annotations

from .openai_client import (
    LOG_TOKEN_USAGE,
    MAX_COMPLETION_TOKENS,
    MAX_INPUT_TOKENS,
    MAX_MESSAGE_CHARS,
    MAX_TOOL_CHARS,
    MODEL,
    TOKEN_CHAR_RATIO,
    OpenAIChatClient,
    _estimate_tokens,
    _normalize_messages,
    _truncate_messages,
    _truncate_text,
)

default_client = OpenAIChatClient()


def call_llm(messages, tools=None):
    return default_client.call(messages, tools)
