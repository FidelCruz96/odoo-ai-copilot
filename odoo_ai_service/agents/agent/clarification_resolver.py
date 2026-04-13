from __future__ import annotations

import re
from typing import Any


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _has_count_intent_terms(text: str) -> bool:
    return _contains_any(
        text,
        [
            "cuantos",
            "cuántos",
            "cuantas",
            "cuántas",
            "cantidad",
            "numero",
            "número",
            "total",
            "conteo",
        ],
    )


def _has_list_intent_terms(text: str) -> bool:
    return _contains_any(
        text,
        [
            "muestra",
            "muestrame",
            "muéstrame",
            "muestreme",
            "muéstreme",
            "lista",
            "listar",
            "detalle",
            "ver",
            "dame",
        ],
    )


def _should_clarify_sales_vs_invoices(text: str) -> bool:
    """
    Aclara solo cuando hay señales de ambigüedad real entre ventas y facturas.
    Evita sobre-aclarar preguntas que ya especifican claramente el objeto.
    """
    if not text:
        return False

    invoice_explicit_terms = [
        "factura",
        "facturas",
        "comprobante",
        "comprobantes",
        "invoice",
        "documento fiscal",
    ]
    sales_explicit_terms = [
        "pedido",
        "pedidos",
        "orden de venta",
        "ordenes de venta",
        "órdenes de venta",
        "cotizacion",
        "cotización",
        "cotizaciones",
    ]
    ambiguity_triggers = [
        "ventas pendientes",
        "venta pendiente",
        "facturado",
        "facturados",
        "ingresos",
        "operaciones",
    ]

    if _contains_any(text, invoice_explicit_terms):
        return False
    if _contains_any(text, sales_explicit_terms):
        return False

    if _contains_any(text, ambiguity_triggers):
        return True

    return False


def _should_clarify_count_vs_list(text: str) -> bool:
    """
    Solo dispara cuando hay intención de consulta de estado/listado
    pero falta decidir si el usuario quiere conteo o detalle.
    """
    if not text:
        return False

    ambiguity_terms = [
        "pendiente",
        "pendientes",
        "publicada",
        "publicadas",
        "emitida",
        "emitidas",
        "vencida",
        "vencidas",
        "no pagada",
        "no pagadas",
    ]

    if not _contains_any(text, ambiguity_terms):
        return False

    if _has_count_intent_terms(text) or _has_list_intent_terms(text):
        return False

    return True


CLARIFICATION_RULES = [
    {
        "name": "sales_vs_invoices_scope",
        "match_patterns": [
            r"\bventas?\s+pendientes?\b",
            r"\bfacturad[oa]s?\b",
            r"\bingresos?\b",
            r"\boperaciones?\b",
        ],
        "question": "¿Te refieres a pedidos de venta o a facturas emitidas?",
        "choices": {
            "sale_orders": {
                "answer_patterns": [
                    r"\bpedido[s]?\b",
                    r"\borden(?:es)?\b",
                    r"\border(?:es)?\s+de\s+venta\b",
                    r"\bventa[s]?\b",
                ],
                "rewrite_template": "consulta enfocada en pedidos de venta: {original_question}",
            },
            "invoices": {
                "answer_patterns": [
                    r"\bfactura[s]?\b",
                    r"\bcomprobante[s]?\b",
                    r"\bemiti[dt]a[s]?\b",
                    r"\bdocumento[s]?\s+fiscal(?:es)?\b",
                ],
                "rewrite_template": "consulta enfocada en facturas emitidas (out_invoice): {original_question}",
            },
        },
    },
    {
        "name": "top_sale_scope",
        "match_patterns": [
            r"\bmayor venta\b",
            r"\bventa mas alta\b",
            r"\bventa más alta\b",
            r"\bventa de mayor monto\b",
            r"\bventa mas grande\b",
            r"\bventa más grande\b",
        ],
        "question": "¿Te refieres a la orden de venta individual más alta o al total vendido del período?",
        "choices": {
            "individual": {
                "answer_patterns": [
                    r"\bindividual\b",
                    r"\bpedido\b",
                    r"\borden\b",
                    r"\bventa individual\b",
                    r"\bla orden\b",
                ],
                "rewrite_template": "dime la orden de venta individual más alta del período para: {original_question}",
            },
            "total": {
                "answer_patterns": [
                    r"\btotal\b",
                    r"\btotal vendido\b",
                    r"\bacumulado\b",
                    r"\bsuma\b",
                    r"\bimporte total\b",
                ],
                "rewrite_template": "dime el total vendido del período para: {original_question}",
            },
        },
    },
    {
        "name": "count_vs_list_scope",
        "match_patterns": [
            r"\bpendiente[s]?\b",
            r"\bpublicad[oa]s?\b",
            r"\bemitid[oa]s?\b",
            r"\bvencid[oa]s?\b",
            r"\bno\s+pagad[oa]s?\b",
        ],
        "question": "¿Quieres solo el total o quieres ver el detalle?",
        "choices": {
            "count": {
                "answer_patterns": [
                    r"\btotal\b",
                    r"\bcantidad\b",
                    r"\bnumero\b",
                    r"\bnúmero\b",
                    r"\bconteo\b",
                    r"\bsolo\b.*\btotal\b",
                ],
                "rewrite_template": "¿cuántos hay en total para: {original_question}?",
            },
            "list": {
                "answer_patterns": [
                    r"\bdetalle\b",
                    r"\blista\b",
                    r"\bmostrar\b",
                    r"\bver\b",
                    r"\bcompleto\b",
                    r"\btodos\b",
                ],
                "rewrite_template": "muéstrame el detalle para: {original_question}",
            },
        },
    },
    {
        "name": "top_purchase_scope",
        "match_patterns": [
            r"\bmayor compra\b",
            r"\bcompra mas alta\b",
            r"\bcompra más alta\b",
            r"\bcompra de mayor monto\b",
            r"\bcompra mas grande\b",
            r"\bcompra más grande\b",
        ],
        "question": "¿Te refieres a la orden de compra individual más alta o al total comprado del período?",
        "choices": {
            "individual": {
                "answer_patterns": [
                    r"\bindividual\b",
                    r"\borden\b",
                    r"\bcompra individual\b",
                    r"\bla orden\b",
                ],
                "rewrite_template": "dime la orden de compra individual más alta del período para: {original_question}",
            },
            "total": {
                "answer_patterns": [
                    r"\btotal\b",
                    r"\btotal comprado\b",
                    r"\bacumulado\b",
                    r"\bsuma\b",
                    r"\bimporte total\b",
                ],
                "rewrite_template": "dime el total comprado del período para: {original_question}",
            },
        },
    },
]


def _normalize_text(text: str) -> str:
    return (text or "").strip().lower()


def _find_rule_by_name(rule_name: str) -> dict[str, Any] | None:
    for rule in CLARIFICATION_RULES:
        if rule["name"] == rule_name:
            return rule
    return None


def detect_clarification_needed(question: str, memory: dict[str, Any] | None) -> dict[str, Any] | None:
    if not question:
        return None
    memory = memory if isinstance(memory, dict) else {}
    if isinstance(memory.get("pending_clarification"), dict):
        return None

    text = _normalize_text(question)
    for rule in CLARIFICATION_RULES:
        if rule["name"] == "sales_vs_invoices_scope" and not _should_clarify_sales_vs_invoices(text):
            continue
        if rule["name"] == "count_vs_list_scope" and not _should_clarify_count_vs_list(text):
            continue
        if any(re.search(pattern, text) for pattern in rule["match_patterns"]):
            return {
                "name": rule["name"],
                "question": rule["question"],
                "original_question": question,
            }
    return None


def resolve_pending_clarification(question: str, memory: dict[str, Any] | None) -> dict[str, Any] | None:
    if not question or not isinstance(memory, dict):
        return None

    pending = memory.get("pending_clarification")
    if not isinstance(pending, dict):
        return None

    rule = _find_rule_by_name(pending.get("name"))
    if not rule:
        return None

    text = _normalize_text(question)
    for choice_name, choice in rule["choices"].items():
        patterns = choice.get("answer_patterns") or []
        if any(re.search(pattern, text) for pattern in patterns):
            original_question = pending.get("original_question") or ""
            rewritten = choice["rewrite_template"].format(
                original_question=original_question,
                answer=question,
                choice=choice_name,
            )
            return {
                "resolved": True,
                "rewritten_question": rewritten,
                "choice": choice_name,
                "rule_name": rule["name"],
            }

    return {
        "resolved": False,
        "question": rule["question"],
        "rule_name": rule["name"],
    }
