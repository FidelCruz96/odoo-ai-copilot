from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    def call(self, messages: list[dict], tools: list[dict] | None = None):
        ...
