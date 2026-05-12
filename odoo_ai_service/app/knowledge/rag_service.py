from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from time import perf_counter
from uuid import uuid4

from openai import OpenAI

from app.core.config import Settings, get_settings
from app.knowledge.embedding_service import EmbeddingService, get_embedding_service
from app.knowledge.schemas import QueryRequest, QueryResponse, SourceItem
from app.knowledge.vector_service import VectorService, get_vector_service

logger = logging.getLogger("odoo_ai_service")


@dataclass
class RagService:
    settings: Settings
    embedding_service: EmbeddingService
    vector_service: VectorService
    client: OpenAI | None = None

    def __post_init__(self) -> None:
        if self.client is None and self.settings.openai_api_key:
            self.client = OpenAI(api_key=self.settings.openai_api_key)

    def answer_query(self, query_request: QueryRequest) -> QueryResponse:
        started_at = perf_counter()
        trace_id = str(uuid4())
        logger.info(
            "RAG_QUERY_START %s",
            json.dumps(
                {
                    "trace_id": trace_id,
                    "query": query_request.query,
                    "filters": query_request.filters or {},
                    "top_k": query_request.top_k or self.settings.top_k,
                    "similarity_threshold": self.settings.similarity_threshold,
                },
                ensure_ascii=False,
            ),
        )
        retrieval_started_at = perf_counter()
        query_embedding = self.embedding_service.embed_query(query_request.query)
        raw_chunks = self.vector_service.search(
            query_embedding=query_embedding,
            top_k=query_request.top_k or self.settings.top_k,
            filters=query_request.filters,
        )
        retrieval_ms = round((perf_counter() - retrieval_started_at) * 1000, 2)
        raw_scores = [round(float(chunk.get("score", 0.0)), 4) for chunk in raw_chunks[:5]]
        filtered_chunks = [
            chunk for chunk in raw_chunks if float(chunk.get("score", 0.0)) >= self.settings.similarity_threshold
        ]
        llm_ms = 0.0
        if filtered_chunks:
            llm_started_at = perf_counter()
            llm_result = self._generate_answer(query_request.query, filtered_chunks)
            llm_ms = round((perf_counter() - llm_started_at) * 1000, 2)
            answer = llm_result["answer"]
            tokens_used = llm_result["tokens_used"]
        else:
            answer = "No encontré suficiente contexto documental para responder con precisión."
            tokens_used = None
        sources = [
            SourceItem(
                doc_id=str(chunk.get("doc_id", "")),
                doc_name=str(chunk.get("doc_name", "")),
                page=chunk.get("page"),
                score=float(chunk.get("score", 0.0)),
            )
            for chunk in filtered_chunks
        ]
        latency_ms = round((perf_counter() - started_at) * 1000, 2)
        logger.info(
            "RAG_QUERY_END %s",
            json.dumps(
                {
                    "trace_id": trace_id,
                    "raw_chunks": len(raw_chunks),
                    "top_score": raw_scores[0] if raw_scores else None,
                    "raw_scores": raw_scores,
                    "filtered_chunks": len(filtered_chunks),
                    "sources_count": len(sources),
                    "latency_ms": latency_ms,
                    "retrieval_ms": retrieval_ms,
                    "llm_ms": llm_ms,
                    "tokens_used": tokens_used,
                },
                ensure_ascii=False,
            ),
        )
        return QueryResponse(
            answer=answer,
            sources=sources,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
            retrieval_ms=retrieval_ms,
            llm_ms=llm_ms,
            raw_chunks=len(raw_chunks),
            filtered_chunks=len(filtered_chunks),
            trace_id=trace_id,
        )

    def _generate_answer(self, query: str, chunks: list[dict]) -> dict:
        context = self._build_context(chunks)
        if not self.settings.openai_api_key:
            return {
                "answer": f"Contexto recuperado:\n{context[:1200]}",
                "tokens_used": None,
            }
        response = self.client.chat.completions.create(
            model=self.settings.ai_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Responde solo con base en el contexto recuperado. "
                        "Si falta evidencia suficiente, dilo explícitamente. "
                        "Sé breve: máximo 4 viñetas o 120 palabras."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Pregunta:\n{query}\n\nContexto:\n{context}",
                },
            ],
            max_completion_tokens=self.settings.rag_max_completion_tokens,
        )
        choice = response.choices[0]
        content = choice.message.content or "No se pudo generar una respuesta con el contexto recuperado."
        tokens_used = getattr(getattr(response, "usage", None), "total_tokens", None)
        return {"answer": content, "tokens_used": tokens_used}

    def _build_context(self, chunks: list[dict]) -> str:
        max_chunks = max(1, self.settings.rag_context_chunks)
        max_chars = max(1, self.settings.rag_context_chars)
        parts = []
        for chunk in chunks[:max_chunks]:
            content = str(chunk.get("content", ""))[:max_chars]
            parts.append(
                f"[{chunk.get('doc_name')} p.{chunk.get('page') or '-'} score={round(float(chunk.get('score', 0.0)), 2)}]\n"
                f"{content}"
            )
        return "\n\n".join(parts)


def get_rag_service() -> RagService:
    return RagService(
        settings=get_settings(),
        embedding_service=get_embedding_service(),
        vector_service=get_vector_service(),
    )
