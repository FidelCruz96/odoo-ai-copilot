from __future__ import annotations

import re
from typing import Any

from .agent_rules import (
    get_clarification_message,
    get_followup_clarification_threshold,
    get_followup_confidence_rules,
)
from .memory_store import get_entity_candidates

ENTITY_FOLLOWUP_PATTERNS = [
    r"\bcual es la compra\b",
    r"\bcuál es la compra\b",
    r"\bcual es la factura\b",
    r"\bcuál es la factura\b",
    r"\bcual es el pedido\b",
    r"\bcuál es el pedido\b",
    r"\bcual es la venta\b",
    r"\bcuál es la venta\b",
    r"\bcual es el documento\b",
    r"\bcuál es el documento\b",
    r"\bcual es la orden\b",
    r"\bcuál es la orden\b",
    r"\bcual fue\b",
    r"\bcuál fue\b",
    r"\besa compra\b",
    r"\besa orden\b",
    r"\besa factura\b",
    r"\bese pedido\b",
    r"\besa venta\b",
    r"\bese documento\b",
    r"\bese asiento\b",
    r"\besa orden de compra\b",
    r"\besa orden de venta\b",
    r"\bmu[eé]stramela\b",
    r"\bmu[eé]strame la compra\b",
    r"\bmu[eé]strame la factura\b",
    r"\bmu[eé]strame el pedido\b",
    r"\bmu[eé]strame la venta\b",
    r"\bmu[eé]strame el documento\b",
    r"\bmu[eé]strame el asiento\b",
    r"\by cual es\b",
    r"\by cuál es\b",
    r"\by la factura\b",
    r"\by el pedido\b",
    r"\by el documento\b",
]

RELATED_INTENT_DEFS = [
    {
        "name": "products",
        "patterns": [r"\bproducto[s]?\b", r"\bitems?\b", r"\bl[ií]neas?\b", r"\bart[ií]culo[s]?\b"],
    },
    {
        "name": "invoices",
        "patterns": [r"\bfactura[s]?\b", r"\bcomprobante[s]?\b", r"\bdocumento[s]?\s+fiscal(?:es)?\b"],
    },
    {
        "name": "related_sales",
        "patterns": [
            r"\bventa[s]?\s+relacionad[oa]s?\b",
            r"\bpedido[s]?\s+relacionad[oa]s?\b",
            r"\bventa[s]?\s+de\s+(?:esta|esa)\s+compra\b",
            r"\bpedido[s]?\s+de\s+(?:esta|esa)\s+compra\b",
        ],
    },
]

RELATED_FOLLOWUP_REFERENCE_PATTERNS = [
    r"\besa\b",
    r"\bese\b",
    r"\besas\b",
    r"\besos\b",
    r"\banterior(?:es)?\b",
    r"\bprevi[oa]s?\b",
    r"\basociad[oa]s?\b",
    r"^\s*y\s+(?:la|el|las|los)\b",
]

RELATED_QUERY_REGISTRY = {
    ("sale.order", "products"): {
        "search": {
            "model": "sale.order.line",
            "domain_builder": lambda entity: [["order_id", "=", entity["id"]]],
        },
        "read": {
            "model": "sale.order.line",
            "fields": ["product_id", "product_uom_qty", "price_unit", "price_subtotal"],
        },
    },
    ("purchase.order", "products"): {
        "search": {
            "model": "purchase.order.line",
            "domain_builder": lambda entity: [["order_id", "=", entity["id"]]],
        },
        "read": {
            "model": "purchase.order.line",
            "fields": ["product_id", "product_qty", "price_unit", "price_subtotal"],
        },
    },
    ("sale.order", "invoices"): {
        "search": {
            "model": "account.move",
            "domain_builder": lambda entity: [
                ["invoice_origin", "=", entity.get("display_name") or entity.get("fields", {}).get("name")],
                ["move_type", "in", ["out_invoice", "out_refund"]],
            ],
        },
        "read": {
            "model": "account.move",
            "fields": ["name", "invoice_date", "amount_total", "state", "move_type"],
        },
    },
    ("purchase.order", "invoices"): {
        "search": {
            "model": "account.move",
            "domain_builder": lambda entity: [
                ["invoice_origin", "=", entity.get("display_name") or entity.get("fields", {}).get("name")],
                ["move_type", "in", ["in_invoice", "in_refund"]],
            ],
        },
        "read": {
            "model": "account.move",
            "fields": ["name", "invoice_date", "amount_total", "state", "move_type"],
        },
    },
    ("purchase.order", "related_sales"): {
        "search": {
            "model": "sale.order",
            "domain_builder": lambda entity: [
                ["rt_purchase_order", "=", entity.get("display_name") or entity.get("fields", {}).get("name")],
            ],
        },
        "read": {
            "model": "sale.order",
            "fields": ["name", "partner_id", "date_order", "amount_total", "state"],
        },
    },
}


def _normalize_text(text: str) -> str:
    return (text or "").strip().lower()


def _match_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _detect_related_intent(text: str) -> str | None:
    for intent_def in RELATED_INTENT_DEFS:
        if _match_any(text, intent_def["patterns"]):
            return intent_def["name"]
    return None


def _has_related_followup_reference(text: str) -> bool:
    return _match_any(text, RELATED_FOLLOWUP_REFERENCE_PATTERNS)


def _is_short_contextual_related_query(text: str) -> bool:
    tokens = re.findall(r"\w+", text or "")
    if len(tokens) == 0 or len(tokens) > 3:
        return False
    if _match_any(
        text,
        [
            r"\beste\s+mes\b",
            r"\bmes\s+pasado\b",
            r"\bsemana\b",
            r"\bhoy\b",
            r"\bayer\b",
            r"\bultim[oa]s?\b",
        ],
    ):
        return False
    return _detect_related_intent(text) is not None


def _build_related_plan(last_entity: dict[str, Any], intent_name: str) -> dict[str, Any] | None:
    config = RELATED_QUERY_REGISTRY.get((last_entity.get("model"), intent_name))
    if not config:
        return None

    domain = config["search"]["domain_builder"](last_entity)
    if not isinstance(domain, list) or not domain:
        return None

    return {
        "type": "related_followup",
        "intent": intent_name,
        "source_model": last_entity["model"],
        "source_id": last_entity["id"],
        "source_display_name": last_entity.get("display_name"),
        "search": {
            "model": config["search"]["model"],
            "domain": domain,
        },
        "read": {
            "model": config["read"]["model"],
            "fields": list(config["read"]["fields"]),
        },
    }


def _related_clarification_question(intent_name: str) -> str:
    if intent_name == "products":
        return get_clarification_message("products", "¿De qué venta o compra quieres ver los productos? Indícame la orden.")
    if intent_name == "invoices":
        return get_clarification_message("invoices", "¿De qué venta o compra quieres ver las facturas? Indícame la orden.")
    if intent_name == "related_sales":
        return get_clarification_message(
            "related_sales",
            "¿De qué compra quieres ver la venta relacionada? Indícame la orden de compra.",
        )
    return "¿A qué registro te refieres exactamente?"


def _entity_model_label(model: str | None) -> str:
    mapping = {
        "sale.order": "venta",
        "purchase.order": "compra",
        "account.move": "factura",
        "sale.order.line": "línea de venta",
        "purchase.order.line": "línea de compra",
    }
    return mapping.get(model or "", "registro")


def _entity_display_name(entity: dict[str, Any] | None) -> str:
    if not isinstance(entity, dict):
        return "sin referencia"
    name = entity.get("display_name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    fields = entity.get("fields")
    if isinstance(fields, dict):
        fallback = fields.get("name")
        if isinstance(fallback, str) and fallback.strip():
            return fallback.strip()
    entity_id = entity.get("id")
    return f"ID {entity_id}" if isinstance(entity_id, int) else "sin referencia"


def _simplify_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for item in candidates:
        entity = item.get("entity") if isinstance(item, dict) else None
        if not isinstance(entity, dict):
            continue
        output.append(
            {
                "source": item.get("source"),
                "model": entity.get("model"),
                "id": entity.get("id"),
                "display_name": _entity_display_name(entity),
            }
        )
    return output


def _has_recent_type_change(memory: dict[str, Any] | None) -> bool:
    if not isinstance(memory, dict):
        return False
    recent = memory.get("recent_entities")
    if not isinstance(recent, list) or len(recent) < 2:
        return False
    valid = [r for r in recent if isinstance(r, dict) and r.get("model") and isinstance(r.get("id"), int)]
    if len(valid) < 2:
        return False
    last = valid[-1]
    prev = valid[-2]
    return last.get("model") != prev.get("model")


def _collect_followup_candidates(last_entity: dict | None, memory: dict | None, intent_name: str) -> list[dict[str, Any]]:
    candidates = []
    if isinstance(memory, dict):
        for item in get_entity_candidates(memory):
            entity = item.get("entity")
            if not isinstance(entity, dict):
                continue
            key = (entity.get("model"), intent_name)
            if key not in RELATED_QUERY_REGISTRY:
                continue
            candidates.append(item)

    if isinstance(last_entity, dict):
        model = last_entity.get("model")
        entity_id = last_entity.get("id")
        if (model, intent_name) in RELATED_QUERY_REGISTRY and isinstance(entity_id, int):
            key = (model, entity_id)
            exists = any(
                isinstance(c.get("entity"), dict)
                and c["entity"].get("model") == key[0]
                and c["entity"].get("id") == key[1]
                for c in candidates
            )
            if not exists:
                candidates.append(
                    {
                        "source": "legacy_last_entity",
                        "model": model,
                        "id": entity_id,
                        "display_name": last_entity.get("display_name"),
                        "entity": last_entity,
                    }
                )
    return candidates


def resolve_followup_entity(
    user_text: str,
    last_entity: dict | None,
    memory: dict | None,
    intent_name: str,
) -> dict[str, Any]:
    text = _normalize_text(user_text)
    has_reference = _has_related_followup_reference(text)
    candidates = _collect_followup_candidates(last_entity, memory, intent_name)
    simplified_candidates = _simplify_candidates(candidates)
    unique_pairs = {
        (c.get("model"), c.get("id"))
        for c in simplified_candidates
        if c.get("model") and isinstance(c.get("id"), int)
    }
    unique_models = {
        model
        for model, _entity_id in unique_pairs
        if isinstance(model, str) and model
    }
    conflict_detected = len(unique_models) > 1 or _has_recent_type_change(memory)

    selected = candidates[0].get("entity") if candidates else None
    source_used = candidates[0].get("source") if candidates else None
    confidence_rules = get_followup_confidence_rules()
    source_weights = confidence_rules.get("source_weights") if isinstance(confidence_rules, dict) else {}

    followup_confidence = 0.0
    if selected:
        try:
            followup_confidence = float(confidence_rules.get("base", 0.65)) if isinstance(confidence_rules, dict) else 0.65
        except Exception:
            followup_confidence = 0.65
        if isinstance(source_weights, dict) and source_used in source_weights:
            try:
                followup_confidence = float(source_weights.get(source_used))
            except Exception:
                pass
        if has_reference:
            try:
                followup_confidence += float(confidence_rules.get("reference_bonus", 0.05))
            except Exception:
                followup_confidence += 0.05
        if conflict_detected and not has_reference:
            try:
                followup_confidence -= float(confidence_rules.get("conflict_penalty", 0.35))
            except Exception:
                followup_confidence -= 0.35
        followup_confidence = max(0.0, min(1.0, followup_confidence))

    return {
        "selected_entity": selected,
        "source_used": source_used,
        "candidates": simplified_candidates,
        "conflict_detected": conflict_detected,
        "followup_confidence": round(followup_confidence, 2),
    }


def _build_ambiguity_question(intent_name: str, candidates: list[dict[str, Any]]) -> str:
    if not candidates or len(candidates) < 2:
        return _related_clarification_question(intent_name)
    first = candidates[0]
    second = candidates[1]
    first_label = _entity_model_label(first.get("model"))
    second_label = _entity_model_label(second.get("model"))
    first_name = first.get("display_name") or "sin referencia"
    second_name = second.get("display_name") or "sin referencia"
    if intent_name == "invoices":
        template = get_clarification_message(
            "ambiguous_invoices",
            "¿Te refieres a la factura de la {first_label} {first_name} o de la {second_label} {second_name}?",
        )
        return template.format(
            first_label=first_label,
            first_name=first_name,
            second_label=second_label,
            second_name=second_name,
        )
    template = get_clarification_message(
        "ambiguous_default",
        "¿Te refieres a la {first_label} {first_name} o a la {second_label} {second_name}?",
    )
    return template.format(
        first_label=first_label,
        first_name=first_name,
        second_label=second_label,
        second_name=second_name,
    )


def needs_followup_clarification(
    user_text: str,
    last_entity: dict | None,
    memory: dict | None = None,
) -> dict | None:
    if not user_text:
        return None

    text = _normalize_text(user_text)
    related_intent = _detect_related_intent(text)
    if not related_intent:
        return None

    if not (_has_related_followup_reference(text) or _is_short_contextual_related_query(text)):
        return None

    selection = resolve_followup_entity(user_text, last_entity, memory, related_intent)
    selected = selection.get("selected_entity")
    if not isinstance(selected, dict):
        return {
            "type": "clarification",
            "intent": related_intent,
            "question": _related_clarification_question(related_intent),
            "reason": "missing_last_entity",
            "entity_candidates": selection.get("candidates") or [],
            "entity_conflict_detected": bool(selection.get("conflict_detected")),
            "followup_confidence": selection.get("followup_confidence"),
        }

    model = selected.get("model")
    record_id = selected.get("id")
    if not model or not isinstance(record_id, int):
        return {
            "type": "clarification",
            "intent": related_intent,
            "question": _related_clarification_question(related_intent),
            "reason": "invalid_last_entity",
            "entity_candidates": selection.get("candidates") or [],
            "entity_conflict_detected": bool(selection.get("conflict_detected")),
            "followup_confidence": selection.get("followup_confidence"),
        }

    if (model, related_intent) not in RELATED_QUERY_REGISTRY:
        return {
            "type": "clarification",
            "intent": related_intent,
            "question": _related_clarification_question(related_intent),
            "reason": "unsupported_source_model",
            "entity_candidates": selection.get("candidates") or [],
            "entity_conflict_detected": bool(selection.get("conflict_detected")),
            "followup_confidence": selection.get("followup_confidence"),
        }

    threshold = get_followup_clarification_threshold()
    if selection.get("conflict_detected") and (selection.get("followup_confidence") or 0.0) < threshold:
        return {
            "type": "clarification",
            "intent": related_intent,
            "question": _build_ambiguity_question(related_intent, selection.get("candidates") or []),
            "reason": "ambiguous_recent_entities",
            "entity_candidates": selection.get("candidates") or [],
            "entity_conflict_detected": True,
            "followup_confidence": selection.get("followup_confidence"),
        }

    return None


def resolve_followup(
    user_text: str,
    last_entity: dict | None,
    memory: dict | None = None,
) -> dict | None:
    if not user_text:
        return None

    text = _normalize_text(user_text)

    related_intent = _detect_related_intent(text)
    if related_intent:
        if not (_has_related_followup_reference(text) or _is_short_contextual_related_query(text)):
            return None
        selection = resolve_followup_entity(user_text, last_entity, memory, related_intent)
        selected_entity = selection.get("selected_entity")
        if not isinstance(selected_entity, dict):
            return None
        if selection.get("conflict_detected") and (selection.get("followup_confidence") or 0.0) < get_followup_clarification_threshold():
            return None
        related_plan = _build_related_plan(selected_entity, related_intent)
        if related_plan:
            related_plan["entity_source_used"] = selection.get("source_used")
            related_plan["entity_candidates"] = selection.get("candidates") or []
            related_plan["entity_conflict_detected"] = bool(selection.get("conflict_detected"))
            related_plan["followup_confidence"] = selection.get("followup_confidence")
            return related_plan

    if not isinstance(last_entity, dict):
        return None
    model = last_entity.get("model")
    record_id = last_entity.get("id")
    if not model or not isinstance(record_id, int):
        return None

    if _match_any(text, ENTITY_FOLLOWUP_PATTERNS):
        return {
            "type": "entity_followup",
            "model": model,
            "id": record_id,
            "display_name": last_entity.get("display_name"),
            "fields": last_entity.get("fields") if isinstance(last_entity.get("fields"), dict) else {},
        }

    return None
