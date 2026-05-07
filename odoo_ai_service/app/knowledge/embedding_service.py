from __future__ import annotations

from dataclasses import dataclass

from openai import OpenAI

from app.core.config import Settings, get_settings


@dataclass
class EmbeddingService:
    settings: Settings
    client: OpenAI | None = None

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = OpenAI(api_key=self.settings.openai_api_key)

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        response = self.client.embeddings.create(model=self.settings.embedding_model, input=texts)
        return [list(item.embedding) for item in response.data]


def get_embedding_service() -> EmbeddingService:
    return EmbeddingService(settings=get_settings())
