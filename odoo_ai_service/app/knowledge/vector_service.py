from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg2
import psycopg2.extras

from app.core.config import Settings, get_settings


@dataclass
class VectorService:
    settings: Settings

    def ping(self) -> bool:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            return True
        except Exception:
            return False

    def ensure_schema(self) -> None:
        dimensions = int(self.settings.embedding_dimensions)
        ddl = f"""
        CREATE EXTENSION IF NOT EXISTS vector;
        CREATE TABLE IF NOT EXISTS ai_document_chunks (
            id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL,
            doc_name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            page INTEGER,
            module TEXT,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            embedding vector({dimensions}) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_ai_document_chunks_doc_id ON ai_document_chunks (doc_id);
        CREATE INDEX IF NOT EXISTS idx_ai_document_chunks_module ON ai_document_chunks (module);
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
            conn.commit()

    def upsert_chunks(self, chunks: list[dict]) -> None:
        if not chunks:
            return
        self.ensure_schema()
        query = """
        INSERT INTO ai_document_chunks (
            id, doc_id, doc_name, source_type, page, module, chunk_index, content, embedding
        )
        VALUES (
            %(id)s, %(doc_id)s, %(doc_name)s, %(source_type)s, %(page)s,
            %(module)s, %(chunk_index)s, %(content)s, %(embedding)s::vector
        )
        ON CONFLICT (id) DO UPDATE SET
            doc_id = EXCLUDED.doc_id,
            doc_name = EXCLUDED.doc_name,
            source_type = EXCLUDED.source_type,
            page = EXCLUDED.page,
            module = EXCLUDED.module,
            chunk_index = EXCLUDED.chunk_index,
            content = EXCLUDED.content,
            embedding = EXCLUDED.embedding;
        """
        payload = []
        for chunk in chunks:
            row = dict(chunk)
            row["embedding"] = _to_pgvector_literal(chunk["embedding"])
            payload.append(row)
        with self._connect() as conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_batch(cur, query, payload, page_size=100)
            conn.commit()

    def search(self, query_embedding: list[float], top_k: int, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        self.ensure_schema()
        where_parts = []
        params: dict[str, Any] = {
            "query_embedding": _to_pgvector_literal(query_embedding),
            "top_k": top_k,
        }
        if filters:
            if filters.get("module"):
                where_parts.append("module = %(module)s")
                params["module"] = filters["module"]
            if filters.get("doc_id"):
                where_parts.append("doc_id = %(doc_id)s")
                params["doc_id"] = filters["doc_id"]
        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        query = f"""
        SELECT
            id,
            doc_id,
            doc_name,
            source_type,
            page,
            module,
            chunk_index,
            content,
            1 - (embedding <=> %(query_embedding)s::vector) AS score
        FROM ai_document_chunks
        {where_clause}
        ORDER BY embedding <=> %(query_embedding)s::vector
        LIMIT %(top_k)s;
        """
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(query, params)
                return [dict(row) for row in (cur.fetchall() or [])]

    def _connect(self):
        if not self.settings.knowledge_database_url:
            raise RuntimeError("KNOWLEDGE_DATABASE_URL is not configured")
        return psycopg2.connect(self.settings.knowledge_database_url, connect_timeout=self.settings.request_timeout_s)


def _to_pgvector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{value:.10f}" for value in embedding) + "]"


def get_vector_service() -> VectorService:
    return VectorService(settings=get_settings())
