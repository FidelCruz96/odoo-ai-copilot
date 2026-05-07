from __future__ import annotations

import json
import logging

from app.knowledge.rag_service import get_rag_service
from app.knowledge.schemas import QueryRequest

logger = logging.getLogger("odoo_ai_service")


def _dump_model(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def search_knowledge(query: str, module: str | None = None, doc_id: str | None = None, top_k: int = 5) -> dict:
    filters = {}
    if module:
        filters["module"] = module
    if doc_id:
        filters["doc_id"] = doc_id
    logger.info(
        "KNOWLEDGE_QUERY_START %s",
        json.dumps(
            {
                "query": query,
                "module": module,
                "doc_id": doc_id,
                "top_k": top_k,
            },
            ensure_ascii=False,
        ),
    )
    response = get_rag_service().answer_query(
        QueryRequest(query=query, filters=filters or None, top_k=top_k)
    )
    result = _dump_model(response)
    logger.info(
        "KNOWLEDGE_QUERY_END %s",
        json.dumps(
            {
                "trace_id": result.get("trace_id"),
                "sources_count": len(result.get("sources") or []),
                "latency_ms": result.get("latency_ms"),
                "tokens_used": result.get("tokens_used"),
            },
            ensure_ascii=False,
        ),
    )
    return result
