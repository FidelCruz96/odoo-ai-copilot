from __future__ import annotations

from app.agents.types import Entity, IntentName

POLICY_VALIDATION_KEYWORDS = [
    "debio",
    "deberia",
    "aprobarse",
    "cumple",
    "segun la politica",
    "segun documentacion",
    "requiere aprobacion",
    "necesita aprobacion",
    "debe aprobarse",
    "entra al flujo",
    "aplica aprobacion",
    "supera el umbral",
    "corresponde aprobar",
    "esta bien segun",
]

INTENT_MAP = {
    "amount_lookup": ["monto", "total", "importe", "valor"],
    "status_lookup": ["estado", "situacion"],
    "count": ["cuantos", "cuantas", "cantidad", "numero de", "numero ", "nro "],
    "ranking": ["top", "mayores", "mas alto", "mayor", "ranking"],
    "line_items": ["productos", "lineas", "items", "detalle"],
    "policy_validation": POLICY_VALIDATION_KEYWORDS,
    "explanation": ["que es", "como funciona", "explica", "documentacion", "manual", "politica", "proceso"],
}


def resolve_intent(text: str, domain: str | None = None, entity: Entity | None = None) -> IntentName | str | None:
    value = text or ""

    if any(keyword in value for keyword in INTENT_MAP["policy_validation"]):
        return "policy_validation"

    if entity and "segun" in value and domain in {"purchase", "sale", "invoice", "inventory"}:
        return "policy_validation"

    if any(keyword in value for keyword in INTENT_MAP["explanation"]):
        return "explanation"

    if "segun" in value and domain in {"knowledge", "purchase", "sale", "invoice", "inventory"}:
        return "explanation"

    amount_hint = any(keyword in value for keyword in INTENT_MAP["amount_lookup"])
    if amount_hint:
        return "amount_lookup"
    if "cuanto" in value and any(keyword in value for keyword in ("monto", "total", "importe", "valor")):
        return "amount_lookup"
    if "cuanto" in value and isinstance(entity, dict) and entity.get("type") in {"purchase_order", "sale_order", "invoice"}:
        return "amount_lookup"

    if any(keyword in value for keyword in INTENT_MAP["count"]):
        return "count"

    if any(keyword in value for keyword in INTENT_MAP["ranking"]):
        return "ranking"

    if any(keyword in value for keyword in INTENT_MAP["status_lookup"]):
        return "status_lookup"

    if any(keyword in value for keyword in INTENT_MAP["line_items"]):
        return "line_items"

    if domain == "knowledge":
        return "explanation"
    return None
