from __future__ import annotations

from app.agents.types import ContextResolution, Entity
from app.memory.schemas import ActiveEntity, ConversationMemory


CONTEXT_REQUIRED_INTENTS = {
    "amount_lookup",
    "status_lookup",
    "line_items",
    "policy_validation",
}


def _active_entity_to_context(active_entity: ActiveEntity) -> Entity:
    return {
        "type": active_entity.type,
        "model": active_entity.model,
        "id": active_entity.id,
        "name": active_entity.name,
        "confidence": active_entity.confidence,
    }


def _active_entity_matches_domain(active_entity: ActiveEntity, target_domain: str | None) -> bool:
    if not target_domain:
        return True
    if target_domain == "invoice":
        return active_entity.model == "account.move"
    return active_entity.model.startswith(f"{target_domain}.")


def _has_contextual_reference(entity: Entity | None, question: str, intent: str | None) -> bool:
    value = question or ""
    if isinstance(entity, dict) and entity.get("type") == "relative_reference":
        return True
    if any(marker in value for marker in ("su ", "esta", "este", "esa", "ese", "anterior")):
        return True
    if intent == "amount_lookup" and any(marker in value for marker in ("el total", "total")):
        return True
    return False


def resolve_context(
    entity: Entity | None,
    memory: ConversationMemory | None,
    *,
    intent: str | None = None,
    domain: str | None = None,
    question: str = "",
) -> ContextResolution:
    active_entity = memory.active_entity if isinstance(memory, ConversationMemory) else None
    has_relative_reference = isinstance(entity, dict) and entity.get("type") == "relative_reference"

    if has_relative_reference:
        target_domain = entity.get("target_domain")
        if active_entity and _active_entity_matches_domain(active_entity, target_domain):
            return {
                "entity": _active_entity_to_context(active_entity),
                "memory_hit": True,
                "needs_clarification": False,
            }
        example = "PO-I-10-00026" if target_domain == "purchase" else "SO-2024-00015"
        label = "compra" if target_domain == "purchase" else "registro"
        return {
            "entity": None,
            "memory_hit": False,
            "needs_clarification": True,
            "clarification_message": f"¿A qué {label} te refieres? Dame el número de orden, por ejemplo {example}.",
        }

    if isinstance(entity, dict) and entity.get("type") == "business_document_code" and not entity.get("model"):
        code = entity.get("code") or "ese código"
        return {
            "entity": None,
            "memory_hit": False,
            "needs_clarification": True,
            "clarification_message": (
                f"Identifiqué el código {code}, pero necesito saber si corresponde a una compra, venta o factura."
            ),
        }

    if isinstance(entity, dict):
        return {
            "entity": entity,
            "memory_hit": False,
            "needs_clarification": False,
        }

    should_use_memory = (
        intent in CONTEXT_REQUIRED_INTENTS
        and bool(active_entity)
        and _has_contextual_reference(entity, question, intent)
        and _active_entity_matches_domain(active_entity, domain)
    )
    if should_use_memory and active_entity:
        return {
            "entity": _active_entity_to_context(active_entity),
            "memory_hit": True,
            "needs_clarification": False,
        }

    return {
        "entity": None,
        "memory_hit": False,
        "needs_clarification": False,
    }
