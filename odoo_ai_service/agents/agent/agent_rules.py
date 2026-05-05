from __future__ import annotations

import json
import logging
import os
import re
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_AGENT_RULES: dict[str, Any] = {
    "explicit_doc_regex": r"\b(?:PO|SO|DCN|DCE|FC|FAC|INV|P)\s*[-/]?[A-Z0-9-]*\d[A-Z0-9-]*\b",
    "entity_hint_tokens": [
        "orden ",
        "orden de compra",
        "orden de venta",
        "compra ",
        "venta ",
        "factura ",
        "pedido ",
    ],
    "guardrail_terms": {
        "sales_terms": ["venta", "ventas", "pedido", "pedidos", "orden de venta", "ordenes de venta"],
        "purchase_terms": ["compra", "compras", "proveedor", "proveedores", "orden de compra", "ordenes de compra"],
        "invoice_terms": ["factura", "facturas", "comprobante", "comprobantes", "emitida", "emitidas"],
        "pending_terms": ["pendiente", "pendientes"],
        "orders_with_invoice_terms": [
            "con factura",
            "con facturas",
            "que tengan factura",
            "que tengan facturas",
            "tiene factura",
            "tiene facturas",
            "tienen factura",
            "tienen facturas",
            "tenga factura",
            "tenga facturas",
            "con comprobante",
            "con comprobantes",
            "tengan factura",
            "tengan facturas",
        ],
    },
    "invoice_scope_patterns": [
        "esta venta",
        "esa venta",
        "este pedido",
        "ese pedido",
        "esta compra",
        "esa compra",
        "de esta venta",
        "de esa venta",
        "de esta compra",
        "de esa compra",
        "tiene factura",
        "tiene alguna factura",
        "su factura",
        "sus facturas",
        "facturas relacionadas",
    ],
    "clarification": {
        "followup_confidence_threshold": 0.75,
        "followup_confidence": {
            "base": 0.65,
            "source_weights": {
                "last_explicit_entity": 0.95,
                "primary_entity": 0.85,
                "last_ui_entity": 0.60,
            },
            "reference_bonus": 0.05,
            "conflict_penalty": 0.35,
        },
    },
    "clarification_messages": {
        "products": "¿De qué venta o compra quieres ver los productos? Indícame la orden.",
        "invoices": "¿De qué venta o compra quieres ver las facturas? Indícame la orden.",
        "related_sales": "¿De qué compra quieres ver la venta relacionada? Indícame la orden de compra.",
        "ambiguous_invoices": (
            "¿Te refieres a la factura de la {first_label} {first_name} "
            "o de la {second_label} {second_name}?"
        ),
        "ambiguous_default": (
            "¿Te refieres a la {first_label} {first_name} "
            "o a la {second_label} {second_name}?"
        ),
    },
}


def _deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        result = dict(base)
        for key, value in override.items():
            result[key] = _deep_merge(base.get(key), value)
        return result
    if isinstance(base, list) and isinstance(override, list):
        return list(override)
    return override if override is not None else base


def _rules_path() -> Path:
    env_path = os.getenv("AGENT_RULES_PATH")
    if env_path:
        return Path(env_path)
    return Path(__file__).resolve().parents[2] / "config" / "agent_rules.json"


@lru_cache(maxsize=1)
def get_agent_rules() -> dict[str, Any]:
    rules = deepcopy(DEFAULT_AGENT_RULES)
    path = _rules_path()
    if not path.exists():
        return rules

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            rules = _deep_merge(rules, payload)
    except Exception as exc:
        logger.warning("No se pudo cargar config de reglas del agente en %s: %s", path, exc)
    return rules


def get_explicit_doc_regex() -> re.Pattern:
    rules = get_agent_rules()
    pattern = rules.get("explicit_doc_regex")
    if not isinstance(pattern, str) or not pattern.strip():
        pattern = DEFAULT_AGENT_RULES["explicit_doc_regex"]
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        logger.warning("Regex explícito inválido en config; usando default.")
        return re.compile(DEFAULT_AGENT_RULES["explicit_doc_regex"], re.IGNORECASE)


def get_entity_hint_tokens() -> list[str]:
    rules = get_agent_rules()
    tokens = ((rules.get("entity_hint_tokens") or []) if isinstance(rules, dict) else [])
    if isinstance(tokens, list) and tokens:
        return [str(t).lower() for t in tokens if isinstance(t, str) and t.strip()]
    return list(DEFAULT_AGENT_RULES["entity_hint_tokens"])


def get_guardrail_terms() -> dict[str, list[str]]:
    rules = get_agent_rules()
    guardrails = rules.get("guardrail_terms") if isinstance(rules, dict) else None
    defaults = DEFAULT_AGENT_RULES["guardrail_terms"]
    output: dict[str, list[str]] = {}
    for key, default_values in defaults.items():
        values = []
        if isinstance(guardrails, dict):
            raw = guardrails.get(key)
            if isinstance(raw, list):
                values = [str(v).lower() for v in raw if isinstance(v, str) and v.strip()]
        output[key] = values or list(default_values)
    return output


def get_invoice_scope_patterns() -> list[str]:
    rules = get_agent_rules()
    patterns = rules.get("invoice_scope_patterns") if isinstance(rules, dict) else None
    if isinstance(patterns, list) and patterns:
        normalized = [str(v).lower() for v in patterns if isinstance(v, str) and v.strip()]
        if normalized:
            return normalized
    return list(DEFAULT_AGENT_RULES["invoice_scope_patterns"])


def get_followup_confidence_rules() -> dict[str, Any]:
    rules = get_agent_rules()
    clarification = rules.get("clarification") if isinstance(rules, dict) else None
    conf = clarification.get("followup_confidence") if isinstance(clarification, dict) else None
    if isinstance(conf, dict):
        return conf
    return deepcopy(DEFAULT_AGENT_RULES["clarification"]["followup_confidence"])


def get_followup_clarification_threshold() -> float:
    rules = get_agent_rules()
    clarification = rules.get("clarification") if isinstance(rules, dict) else None
    value = clarification.get("followup_confidence_threshold") if isinstance(clarification, dict) else None
    try:
        if value is not None:
            return float(value)
    except Exception:
        pass
    return float(DEFAULT_AGENT_RULES["clarification"]["followup_confidence_threshold"])


def get_clarification_message(key: str, default: str) -> str:
    rules = get_agent_rules()
    messages = rules.get("clarification_messages") if isinstance(rules, dict) else None
    if isinstance(messages, dict):
        value = messages.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return default
