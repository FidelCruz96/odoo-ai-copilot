from __future__ import annotations

from typing import Any
from datetime import datetime

from pydantic import BaseModel, Field


class ActiveEntity(BaseModel):
    type: str
    model: str
    id: int
    name: str | None = None
    confidence: float = 1.0


class ConversationMemory(BaseModel):
    session_id: str
    user_id: int | None = None
    db_name: str | None = None
    active_entity: ActiveEntity | None = None
    active_domain: str | None = None
    last_route: str | None = None
    last_intent: str | None = None
    last_question: str | None = None
    last_fields: dict[str, Any] = Field(default_factory=dict)
    last_tools_used: list[str] = Field(default_factory=list)
    last_sources: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    expires_at: datetime | None = None

    def to_context_dict(self) -> dict[str, Any]:
        payload = {
            "user_id": self.user_id,
            "db_name": self.db_name,
            "active_domain": self.active_domain,
            "last_route": self.last_route,
            "last_intent": self.last_intent,
            "last_question": self.last_question,
            "last_fields": dict(self.last_fields or {}),
            "last_tools_used": list(self.last_tools_used or []),
            "last_sources": list(self.last_sources or []),
            "metadata": dict(self.metadata or {}),
        }
        if self.active_entity:
            active = self.active_entity.model_dump() if hasattr(self.active_entity, "model_dump") else self.active_entity.dict()
            payload["active_entity"] = active
            payload["last_entity"] = {
                "model": active.get("model"),
                "id": active.get("id"),
                "display_name": active.get("name"),
                "fields": dict(self.last_fields or {}),
            }
        return payload
