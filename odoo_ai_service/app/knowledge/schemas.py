from __future__ import annotations

from pydantic import BaseModel, Field


class SourceItem(BaseModel):
    doc_id: str
    doc_name: str
    page: int | None = None
    score: float


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)
    session_id: str | None = None
    filters: dict | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceItem]
    tokens_used: int | None = None
    latency_ms: float
    trace_id: str


class IngestedDocument(BaseModel):
    file: str
    chunks: int
    status: str


class IngestResponse(BaseModel):
    ingested: list[IngestedDocument]
