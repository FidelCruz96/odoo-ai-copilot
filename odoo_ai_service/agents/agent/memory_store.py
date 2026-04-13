from __future__ import annotations

from typing import Any


PRIMARY_MODELS = {"sale.order", "purchase.order", "account.move", "res.partner"}
SECONDARY_MODELS = {"sale.order.line", "purchase.order.line"}


def _normalize_entity(entity: dict[str, Any] | None, source_query: str | None = None) -> dict[str, Any] | None:
    if not isinstance(entity, dict):
        return None

    fields = entity.get("fields")
    return {
        "model": entity.get("model"),
        "id": entity.get("id"),
        "display_name": entity.get("display_name"),
        "fields": fields if isinstance(fields, dict) else {},
        "source_query": source_query,
    }


def get_session_memory(context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(context, dict):
        return {}
    memory = context.get("memory")
    return memory if isinstance(memory, dict) else {}


def get_last_entity(context: dict[str, Any] | None) -> dict[str, Any] | None:
    memory = get_session_memory(context)
    primary_entity = memory.get("primary_entity")
    if isinstance(primary_entity, dict):
        return primary_entity
    last_entity = memory.get("last_entity")
    return last_entity if isinstance(last_entity, dict) else None


def update_last_entity(memory: dict[str, Any] | None, entity: dict[str, Any] | None, source_query: str | None = None) -> dict[str, Any]:
    payload = dict(memory) if isinstance(memory, dict) else {}
    entity_payload = _normalize_entity(entity, source_query=source_query)
    if not entity_payload:
        return payload

    model = entity_payload.get("model")
    current_primary = payload.get("primary_entity")
    has_primary = isinstance(current_primary, dict)

    if model in PRIMARY_MODELS or not has_primary:
        payload["primary_entity"] = entity_payload
        payload["last_entity"] = entity_payload
    elif model in SECONDARY_MODELS:
        payload["secondary_entity"] = entity_payload
        if has_primary:
            payload["last_entity"] = current_primary
    else:
        # Fallback conservador: mantener entidad principal y registrar secundaria.
        payload["secondary_entity"] = entity_payload
        if has_primary:
            payload["last_entity"] = current_primary
        else:
            payload["primary_entity"] = entity_payload
            payload["last_entity"] = entity_payload

    return payload


def set_pending_clarification(memory: dict[str, Any] | None, clarification: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(memory) if isinstance(memory, dict) else {}
    if isinstance(clarification, dict):
        payload["pending_clarification"] = clarification
    else:
        payload.pop("pending_clarification", None)
    return payload
