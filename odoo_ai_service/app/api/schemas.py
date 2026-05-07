from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    session_id: str | None = None
    context: dict[str, Any] | None = None
    history: list[dict[str, Any]] | None = None


class KnowledgeQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)
    session_id: str | None = None
    module: str | None = None
    doc_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)
