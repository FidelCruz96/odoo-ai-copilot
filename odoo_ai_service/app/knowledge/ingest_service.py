from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings, get_settings
from app.knowledge.chunking import build_chunks
from app.knowledge.embedding_service import EmbeddingService, get_embedding_service
from app.knowledge.file_parser import build_doc_id, parse_document_bytes, validate_ingest_file
from app.knowledge.schemas import IngestResponse, IngestedDocument
from app.knowledge.vector_service import VectorService, get_vector_service


@dataclass
class IngestService:
    settings: Settings
    embedding_service: EmbeddingService
    vector_service: VectorService

    def ingest_files(self, files: list[tuple[str, bytes]], module: str | None = None) -> IngestResponse:
        ingested: list[IngestedDocument] = []
        for filename, content in files:
            validate_ingest_file(filename, content, self.settings.max_upload_size_mb)
            pages = parse_document_bytes(content=content, filename=filename)
            source_type = Path(filename).suffix.lower().lstrip(".") or "unknown"
            doc_id = build_doc_id(filename)
            chunk_records = build_chunks(
                pages=pages,
                doc_id=doc_id,
                doc_name=filename,
                source_type=source_type,
                module=module,
                chunk_size=self.settings.chunk_size,
                overlap=self.settings.chunk_overlap,
            )
            if not chunk_records:
                ingested.append(IngestedDocument(file=filename, chunks=0, status="empty"))
                continue
            embeddings = self.embedding_service.embed_texts([chunk["content"] for chunk in chunk_records])
            embedded = []
            for chunk, embedding in zip(chunk_records, embeddings):
                row = dict(chunk)
                row["embedding"] = embedding
                embedded.append(row)
            self.vector_service.upsert_chunks(embedded)
            ingested.append(IngestedDocument(file=filename, chunks=len(embedded), status="ok"))
        return IngestResponse(ingested=ingested)


def get_ingest_service() -> IngestService:
    return IngestService(
        settings=get_settings(),
        embedding_service=get_embedding_service(),
        vector_service=get_vector_service(),
    )
