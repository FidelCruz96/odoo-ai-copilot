from __future__ import annotations

import time
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
        "updated_at": int(time.time()),
    }


def get_session_memory(context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(context, dict):
        return {}
    memory = context.get("memory")
    return memory if isinstance(memory, dict) else {}


def get_last_entity(context: dict[str, Any] | None) -> dict[str, Any] | None:
    memory = get_session_memory(context)
    last_explicit = memory.get("last_explicit_entity")
    if isinstance(last_explicit, dict):
        return last_explicit
    primary_entity = memory.get("primary_entity")
    if isinstance(primary_entity, dict):
        return primary_entity
    last_ui = memory.get("last_ui_entity")
    if isinstance(last_ui, dict):
        return last_ui
    last_inferred = memory.get("last_inferred_entity")
    if isinstance(last_inferred, dict):
        return last_inferred
    last_entity = memory.get("last_entity")
    return last_entity if isinstance(last_entity, dict) else None


def get_entity_candidates(memory: dict[str, Any] | None) -> list[dict[str, Any]]:
    payload = memory if isinstance(memory, dict) else {}
    ordered = [
        ("last_explicit_entity", payload.get("last_explicit_entity")),
        ("primary_entity", payload.get("primary_entity")),
        ("last_ui_entity", payload.get("last_ui_entity")),
        ("last_inferred_entity", payload.get("last_inferred_entity")),
        ("last_entity", payload.get("last_entity")),
    ]
    output = []
    seen = set()
    for source, entity in ordered:
        if not isinstance(entity, dict):
            continue
        model = entity.get("model")
        entity_id = entity.get("id")
        if not model or not isinstance(entity_id, int):
            continue
        key = (model, entity_id)
        if key in seen:
            continue
        seen.add(key)
        output.append(
            {
                "source": source,
                "model": model,
                "id": entity_id,
                "display_name": entity.get("display_name"),
                "entity": entity,
            }
        )
    return output


def _append_recent_entity(payload: dict[str, Any], entity_payload: dict[str, Any], source: str) -> None:
    model = entity_payload.get("model")
    entity_id = entity_payload.get("id")
    if not model or not isinstance(entity_id, int):
        return
    recent = payload.get("recent_entities")
    if not isinstance(recent, list):
        recent = []
    row = {
        "model": model,
        "id": entity_id,
        "display_name": entity_payload.get("display_name"),
        "source": source,
        "updated_at": entity_payload.get("updated_at"),
    }
    if recent:
        last = recent[-1]
        if (
            isinstance(last, dict)
            and last.get("model") == row["model"]
            and last.get("id") == row["id"]
        ):
            recent[-1] = row
            payload["recent_entities"] = recent[-5:]
            return
    recent.append(row)
    payload["recent_entities"] = recent[-5:]


def set_last_ui_entity(memory: dict[str, Any] | None, entity: dict[str, Any] | None, source_query: str | None = None) -> dict[str, Any]:
    payload = dict(memory) if isinstance(memory, dict) else {}
    entity_payload = _normalize_entity(entity, source_query=source_query)
    if not entity_payload:
        return payload
    entity_payload["source"] = "ui"
    payload["last_ui_entity"] = entity_payload
    if not isinstance(payload.get("primary_entity"), dict):
        payload["primary_entity"] = entity_payload
        payload["last_entity"] = entity_payload
        _append_recent_entity(payload, entity_payload, "ui")
    return payload


def update_last_entity(
    memory: dict[str, Any] | None,
    entity: dict[str, Any] | None,
    source_query: str | None = None,
    source: str = "inferred",
) -> dict[str, Any]:
    payload = dict(memory) if isinstance(memory, dict) else {}
    entity_payload = _normalize_entity(entity, source_query=source_query)
    if not entity_payload:
        return payload

    model = entity_payload.get("model")
    entity_payload["source"] = source
    current_primary = payload.get("primary_entity")
    has_primary = isinstance(current_primary, dict)

    if source == "explicit":
        payload["last_explicit_entity"] = entity_payload
    elif source == "inferred":
        payload["last_inferred_entity"] = entity_payload
    elif source == "ui":
        payload["last_ui_entity"] = entity_payload

    should_promote_primary = False
    if source == "explicit":
        should_promote_primary = model in PRIMARY_MODELS or not has_primary
    elif model in PRIMARY_MODELS or not has_primary:
        should_promote_primary = True

    if should_promote_primary:
        payload["primary_entity"] = entity_payload
        payload["last_entity"] = entity_payload
        _append_recent_entity(payload, entity_payload, source)
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
            _append_recent_entity(payload, entity_payload, source)

    return payload


def set_pending_clarification(memory: dict[str, Any] | None, clarification: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(memory) if isinstance(memory, dict) else {}
    if isinstance(clarification, dict):
        payload["pending_clarification"] = clarification
    else:
        payload.pop("pending_clarification", None)
    return payload
