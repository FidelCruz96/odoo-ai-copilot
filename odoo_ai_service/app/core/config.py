from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Odoo Ops Copilot")
    app_version: str = os.getenv("APP_VERSION", "0.2.0")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    ai_model: str = os.getenv("AI_MODEL", os.getenv("LLM_MODEL", "gpt-4o-mini"))
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
    knowledge_database_url: str | None = os.getenv("KNOWLEDGE_DATABASE_URL") or os.getenv("DATABASE_URL")
    top_k: int = int(os.getenv("TOP_K", "5"))
    similarity_threshold: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.70"))
    max_upload_size_mb: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
    request_timeout_s: int = int(os.getenv("REQUEST_TIMEOUT_S", "20"))
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "800"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "100"))
    embedding_dimensions: int = int(os.getenv("EMBEDDING_DIMENSIONS", "3072"))
    enable_knowledge: bool = _as_bool(os.getenv("ENABLE_KNOWLEDGE"), default=True)
    ai_service_api_key: str | None = os.getenv("AI_SERVICE_API_KEY") or os.getenv("ODOO_AI_TOKEN")
    ai_service_auth_required: bool = _as_bool(os.getenv("AI_SERVICE_AUTH_REQUIRED"), default=True)


_SETTINGS = Settings()


def get_settings() -> Settings:
    return _SETTINGS
