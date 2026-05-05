from __future__ import annotations

import logging
import os

from openai import APIConnectionError, APIError, OpenAI, RateLimitError

logger = logging.getLogger("odoo_ai_service")

MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
MAX_INPUT_TOKENS = int(os.getenv("LLM_MAX_INPUT_TOKENS", "80000"))
MAX_COMPLETION_TOKENS = int(os.getenv("LLM_MAX_COMPLETION_TOKENS", "512"))
MAX_MESSAGE_CHARS = int(os.getenv("LLM_MAX_MESSAGE_CHARS", "24000"))
MAX_TOOL_CHARS = int(os.getenv("LLM_MAX_TOOL_CHARS", "12000"))
TOKEN_CHAR_RATIO = float(os.getenv("LLM_TOKEN_CHAR_RATIO", "4.0"))
LOG_TOKEN_USAGE = os.getenv("LLM_LOG_TOKEN_USAGE", "true").lower() in ("1", "true", "yes", "y", "on")


def _estimate_tokens(text):
    if not text:
        return 0
    return int(len(text) / TOKEN_CHAR_RATIO) + 1


def _truncate_text(text, max_chars):
    if not text or len(text) <= max_chars:
        return text
    return text[: max_chars - 16] + " ...[truncated]"


def _normalize_messages(messages):
    normalized = []
    for msg in messages:
        m = dict(msg)
        content = m.get("content", "")
        if content is None:
            content = ""
        if not isinstance(content, str):
            content = str(content)
        if m.get("role") == "tool":
            content = _truncate_text(content, MAX_TOOL_CHARS)
        else:
            content = _truncate_text(content, MAX_MESSAGE_CHARS)
        m["content"] = content
        normalized.append(m)
    return normalized


def _truncate_messages(messages, max_tokens):
    messages = _normalize_messages(messages)
    if not messages:
        return messages

    def total_tokens(msgs):
        return sum(_estimate_tokens(m.get("content", "")) for m in msgs)

    if total_tokens(messages) <= max_tokens:
        return messages

    system_msgs = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]

    while non_system and total_tokens(system_msgs + non_system) > max_tokens:
        non_system.pop(0)

    trimmed = system_msgs + non_system
    if total_tokens(trimmed) <= max_tokens:
        return trimmed

    if trimmed:
        last = dict(trimmed[-1])
        content = last.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        budget = max_tokens - total_tokens(trimmed[:-1])
        max_chars = max(0, int(budget * TOKEN_CHAR_RATIO))
        last["content"] = _truncate_text(content, max_chars)
        trimmed[-1] = last

    return trimmed


class OpenAIChatClient:
    def __init__(self, client=None):
        self.client = client or OpenAI()

    def call(self, messages: list[dict], tools: list[dict] | None = None):
        trimmed_messages = _truncate_messages(messages, MAX_INPUT_TOKENS)
        if LOG_TOKEN_USAGE:
            est_input = sum(_estimate_tokens(m.get("content", "")) for m in trimmed_messages)
            logger.info("LLM estimated input tokens=%s", est_input)

        params = {
            "model": MODEL,
            "messages": trimmed_messages,
            "max_completion_tokens": MAX_COMPLETION_TOKENS,
        }

        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"

        try:
            response = self.client.chat.completions.create(**params)
        except RateLimitError as e:
            logger.warning("LLM rate limit: %s", e)
            raise
        except (APIError, APIConnectionError) as e:
            logger.exception("LLM API error: %s", e)
            raise

        if LOG_TOKEN_USAGE and hasattr(response, "usage") and response.usage:
            logger.info(
                "LLM usage prompt=%s completion=%s total=%s",
                getattr(response.usage, "prompt_tokens", None),
                getattr(response.usage, "completion_tokens", None),
                getattr(response.usage, "total_tokens", None),
            )

        return response
