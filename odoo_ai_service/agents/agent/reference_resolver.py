from __future__ import annotations

import re
from typing import Any

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
            "domain_builder": lambda entity: [["invoice_origin", "=", entity.get("display_name") or entity.get("fields", {}).get("name")]],
        },
        "read": {
            "model": "account.move",
            "fields": ["name", "invoice_date", "amount_total", "state", "move_type"],
        },
    },
    ("purchase.order", "invoices"): {
        "search": {
            "model": "account.move",
            "domain_builder": lambda entity: [["invoice_origin", "=", entity.get("display_name") or entity.get("fields", {}).get("name")]],
        },
        "read": {
            "model": "account.move",
            "fields": ["name", "invoice_date", "amount_total", "state", "move_type"],
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


def resolve_followup(user_text: str, last_entity: dict | None) -> dict | None:
    if not user_text or not isinstance(last_entity, dict):
        return None

    text = _normalize_text(user_text)
    model = last_entity.get("model")
    record_id = last_entity.get("id")
    if not model or not isinstance(record_id, int):
        return None

    related_intent = _detect_related_intent(text)
    if related_intent:
        if not (_has_related_followup_reference(text) or _is_short_contextual_related_query(text)):
            return None
        related_plan = _build_related_plan(last_entity, related_intent)
        if related_plan:
            return related_plan

    if _match_any(text, ENTITY_FOLLOWUP_PATTERNS):
        return {
            "type": "entity_followup",
            "model": model,
            "id": record_id,
            "display_name": last_entity.get("display_name"),
            "fields": last_entity.get("fields") if isinstance(last_entity.get("fields"), dict) else {},
        }

    return None
