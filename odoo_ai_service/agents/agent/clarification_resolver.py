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

    # No aclarar cuando la intención ya es específica para flujos determinísticos del demo.
    deterministic_rank = (
        "cliente" in text
        and "factura" in text
        and _contains_any(text, ["vencida", "vencidas", "atrasada", "atrasadas"])
        and _contains_any(text, ["mas", "más", "top"])
    )
    deterministic_purchase_pending = (
        _contains_any(text, ["orden de compra", "ordenes de compra", "órdenes de compra", "compra", "compras"])
        and _contains_any(text, ["recepcion", "recepción", "por recibir"])
    )
    deterministic_picking_pending = (
        _contains_any(text, ["picking", "pickings"])
        and _contains_any(text, ["validar", "validacion", "validación"])
        and "hoy" in text
    )
    if deterministic_rank or deterministic_purchase_pending or deterministic_picking_pending:
        return False

    if _has_count_intent_terms(text) or _has_list_intent_terms(text):
        return False

    return True


def _should_clarify_period_metric(text: str) -> bool:
    if not text:
        return False
    business_terms = [
        "venta",
        "ventas",
        "compra",
        "compras",
        "facturacion",
        "facturación",
        "factura",
        "facturas",
    ]
    period_terms = [
        "del mes",
        "este mes",
        "mes actual",
        "del periodo",
        "del período",
        "este periodo",
        "este período",
    ]
    explicit_metric_terms = [
        "cuantos",
        "cuántos",
        "cuantas",
        "cuántas",
        "cantidad",
        "numero",
        "número",
        "monto",
        "importe",
        "total vendido",
        "total comprado",
        "top",
        "ranking",
        "cliente",
        "clientes",
        "mas",
        "más",
        "mayor",
        "mayores",
        "detalle",
        "lista",
        "muestra",
        "muestrame",
        "muéstrame",
    ]
    return (
        _contains_any(text, business_terms)
        and _contains_any(text, period_terms)
        and not _contains_any(text, explicit_metric_terms)
    )


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
        "name": "period_metric_scope",
        "match_patterns": [
            r"\bventas?\b.*\b(?:del|este)\s+mes\b",
            r"\bcompras?\b.*\b(?:del|este)\s+mes\b",
            r"\bfacturaci[oó]n\b.*\b(?:del|este)\s+mes\b",
            r"\bfacturas?\b.*\b(?:del|este)\s+mes\b",
            r"\b(?:del|este)\s+mes\b.*\bventas?\b",
            r"\b(?:del|este)\s+mes\b.*\bcompras?\b",
            r"\b(?:del|este)\s+mes\b.*\bfacturaci[oó]n\b",
            r"\b(?:del|este)\s+mes\b.*\bfacturas?\b",
        ],
        "question": "¿Quieres cantidad, monto total o detalle del período?",
        "choices": {
            "count": {
                "answer_patterns": [
                    r"\bcantidad\b",
                    r"\bcuantos\b",
                    r"\bcuántos\b",
                    r"\bcuantas\b",
                    r"\bcuántas\b",
                    r"\bnumero\b",
                    r"\bnúmero\b",
                    r"\bconteo\b",
                ],
                "rewrite_template": "cantidad para: {original_question}",
            },
            "amount": {
                "answer_patterns": [
                    r"\bmonto\b",
                    r"\bimporte\b",
                    r"\btotal\b",
                    r"\bsuma\b",
                    r"\bacumulado\b",
                ],
                "rewrite_template": "monto total para: {original_question}",
            },
            "detail": {
                "answer_patterns": [
                    r"\bdetalle\b",
                    r"\blista\b",
                    r"\bmostrar\b",
                    r"\bver\b",
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


def _match_dynamic_option(answer_text: str, option: dict[str, Any]) -> bool:
    if not isinstance(option, dict):
        return False
    text = _normalize_text(answer_text)
    if not text:
        return False
    candidates = []
    for key in ("key", "value", "label", "display_name"):
        value = option.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(_normalize_text(value))
    for candidate in candidates:
        if not candidate:
            continue
        if text == candidate:
            return True
        if len(text) >= 5 and candidate in text:
            return True
        if len(candidate) >= 8 and text in candidate:
            return True

    option_id = option.get("id")
    if isinstance(option_id, int):
        if re.search(rf"\b{option_id}\b", text):
            return True

    # Fallback semántico conservador: requiere keyword de modelo + token distintivo.
    model = _normalize_text(option.get("model") if isinstance(option.get("model"), str) else "")
    display = _normalize_text(option.get("display_name") if isinstance(option.get("display_name"), str) else "")
    distinctive_tokens = [
        tok for tok in re.findall(r"[a-z0-9]{3,}", display)
        if tok not in {"venta", "compra", "pedido", "orden", "id"}
    ]
    if model == "purchase.order" and "compra" in text:
        return any(tok in text for tok in distinctive_tokens)
    if model == "sale.order" and ("venta" in text or "pedido" in text):
        return any(tok in text for tok in distinctive_tokens)
    return False


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
        if rule["name"] == "period_metric_scope" and not _should_clarify_period_metric(text):
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

    if pending.get("name") == "entity_followup_scope":
        options = pending.get("options") or []
        for option in options:
            if _match_dynamic_option(question, option):
                model = option.get("model")
                entity_id = option.get("id")
                display_name = option.get("display_name") or option.get("label")
                selected_entity = None
                if isinstance(model, str) and isinstance(entity_id, int):
                    selected_entity = {
                        "model": model,
                        "id": entity_id,
                        "display_name": display_name,
                        "fields": {"name": display_name} if isinstance(display_name, str) else {},
                    }
                return {
                    "resolved": True,
                    "rewritten_question": pending.get("original_question") or "",
                    "choice": option.get("key"),
                    "rule_name": pending.get("name"),
                    "selected_entity": selected_entity,
                }
        return {
            "resolved": False,
            "question": pending.get("question") or "¿A qué documento te refieres?",
            "rule_name": pending.get("name"),
        }

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
