from __future__ import annotations

from app.tools.search_knowledge import search_knowledge


def run_search_knowledge(query: str, filters: dict | None = None, top_k: int = 5) -> dict:
    filters = filters or {}
    return search_knowledge(
        query=query,
        module=filters.get("module"),
        doc_id=filters.get("doc_id"),
        top_k=top_k,
    )
