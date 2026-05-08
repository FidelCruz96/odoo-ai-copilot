from __future__ import annotations

from app.agents.types import ContextResolution, Entity
from app.memory.schemas import ActiveEntity, ConversationMemory


def resolve_context(entity: Entity | None, memory: ConversationMemory | None) -> ContextResolution:
    memory_hit = False
    active_entity = memory.active_entity if isinstance(memory, ConversationMemory) else None

    if isinstance(entity, dict) and entity.get("type") == "relative_reference":
        target_domain = entity.get("target_domain")
        if active_entity and active_entity.model.startswith(f"{target_domain}."):
            memory_hit = True
            return {
                "entity": {
                    "type": active_entity.type,
                    "model": active_entity.model,
                    "id": active_entity.id,
                    "name": active_entity.name,
                    "confidence": active_entity.confidence,
                },
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

    if active_entity:
        return {
            "entity": {
                "type": active_entity.type,
                "model": active_entity.model,
                "id": active_entity.id,
                "name": active_entity.name,
                "confidence": active_entity.confidence,
            },
            "memory_hit": True,
            "needs_clarification": False,
        }

    return {
        "entity": None,
        "memory_hit": False,
        "needs_clarification": False,
    }
