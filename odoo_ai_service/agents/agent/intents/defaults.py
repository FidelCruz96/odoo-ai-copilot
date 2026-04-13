from __future__ import annotations

from datetime import date, timedelta
import re
import unicodedata


def _normalize_text(text: str) -> str:
    text = (text or "").lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _month_bounds(year: int, month: int):
    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def _parse_number_token(token: str):
    if token is None:
        return None
    raw = str(token).strip().replace(" ", "")
    if not raw:
        return None

    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        parts = raw.split(",")
        if len(parts[-1]) == 3 and all(p.isdigit() for p in parts):
            raw = "".join(parts)
        else:
            raw = raw.replace(",", ".")
    elif raw.count(".") > 1:
        raw = raw.replace(".", "")

    try:
        return float(raw)
    except Exception:
        return None


def _extract_min_amount(question: str):
    q = _normalize_text(question)
    patterns = [
        r"(?:mayor(?:es)?\s+que|mayor(?:es)?\s+a|mas\s+de|al\s+menos|por\s+lo\s+menos|minimo(?:\s+de)?)\s*(?:s\/)?\s*([\d\.,]+)",
        r"(?:>=|=>)\s*(?:s\/)?\s*([\d\.,]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, q)
        if not match:
            continue
        value = _parse_number_token(match.group(1))
        if value is not None:
            return value

    # Fallback para frases como "por lo menos mil soles"
    if any(k in q for k in ("al menos mil", "por lo menos mil", "mayor a mil", "mas de mil")):
        return 1000.0
    return None


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(k in text for k in keywords)


def _infer_model_from_question(question: str):
    q = _normalize_text(question)

    compras_keywords = ["compra", "compras", "proveedor", "proveedores", "orden de compra", "ordenes de compra"]
    facturas_keywords = ["factura", "facturas", "boleta", "boletas", "nota de credito", "notas de credito"]
    ventas_keywords = ["venta", "ventas", "pedido", "pedidos", "vendedor", "cotizacion", "cotizaciones"]

    if _contains_any(q, facturas_keywords):
        return "account.move"
    if _contains_any(q, compras_keywords):
        return "purchase.order"
    if _contains_any(q, ventas_keywords):
        return "sale.order"
    return None


def _date_field_for_model(model: str):
    if model == "sale.order":
        return "date_order"
    if model == "purchase.order":
        return "date_order"
    if model == "account.move":
        return "invoice_date"
    return None


def _strip_domain_clauses(domain, field_names: set[str], operators: set[str] | None = None):
    cleaned = []
    for clause in domain or []:
        if isinstance(clause, (list, tuple)) and len(clause) == 3:
            field, op, _ = clause
            if field in field_names and (operators is None or op in operators):
                continue
        cleaned.append(clause)
    return cleaned


def _has_domain_clause(domain, field_name: str) -> bool:
    for clause in domain or []:
        if isinstance(clause, (list, tuple)) and len(clause) == 3 and clause[0] == field_name:
            return True
    return False


def detect_period_range(question: str):
    q = _normalize_text(question)
    today = date.today()

    if "ayer" in q:
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday
    if "hoy" in q:
        return today, today

    days_match = re.search(r"(?:ultimos|ultimas)\s+(\d+)\s+dias?", q)
    if days_match:
        days = max(1, int(days_match.group(1)))
        start = today - timedelta(days=days - 1)
        return start, today

    if "semana pasada" in q or "ultima semana" in q:
        current_week_start = today - timedelta(days=today.weekday())
        start = current_week_start - timedelta(days=7)
        end = current_week_start - timedelta(days=1)
        return start, end
    if "esta semana" in q:
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        return start, end
    if "mes pasado" in q or "mes anterior" in q or "ultimo mes" in q:
        last_month_year = today.year if today.month > 1 else today.year - 1
        last_month = today.month - 1 if today.month > 1 else 12
        start, end = _month_bounds(last_month_year, last_month)
        return start, end
    if "este mes" in q or "mes actual" in q:
        start, end = _month_bounds(today.year, today.month)
        return start, end
    if "este ano" in q or "ano actual" in q:
        return date(today.year, 1, 1), date(today.year, 12, 31)
    if "ano pasado" in q:
        y = today.year - 1
        return date(y, 1, 1), date(y, 12, 31)

    # Compatibilidad: si solo dice "semana" o "mes", mantenemos el comportamiento anterior.
    if "semana" in q:
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        return start, end
    if "mes" in q:
        start, end = _month_bounds(today.year, today.month)
        return start, end

    return None


def append_domain(domain, extra):
    if not isinstance(domain, list):
        domain = []
    if not extra:
        return domain
    if isinstance(extra, list):
        domain.extend(extra)
    return domain


def partner_hygiene_domain():
    return [
        ["active", "=", True],
        ["name", "!=", False],
        ["parent_id", "=", False],
    ]


def apply_intent_defaults(intent: str, arguments: dict, question: str) -> dict:
    if not isinstance(arguments, dict):
        return arguments

    if "domain" not in arguments:
        return arguments

    domain = list(arguments.get("domain") or [])

    if intent in ("top_vendedor_por_monto", "top_vendedor_por_pedidos"):
        domain = append_domain(domain, [["user_id", "!=", False]])

    if intent in ("top_cliente_por_monto", "ultimos_clientes_creados"):
        domain = append_domain(domain, partner_hygiene_domain())
        domain = append_domain(domain, [["customer_rank", ">", 0]])

    if intent == "top_cliente_por_monto":
        domain = append_domain(domain, [["partner_id", "!=", False]])
        domain = append_domain(domain, [["partner_id.parent_id", "=", False]])
        domain = append_domain(domain, [["partner_id.active", "=", True]])

    if intent == "ventas_total_periodo":
        has_date = any(
            isinstance(c, (list, tuple)) and len(c) == 3 and c[0] == "date_order"
            for c in domain
        )
        if not has_date:
            period = detect_period_range(question)
            if period:
                start, end = period
                domain = append_domain(domain, [["date_order", ">=", str(start)], ["date_order", "<=", str(end)]])

    arguments["domain"] = domain
    arguments["domain"] = _dedupe_domain(arguments["domain"])
    return arguments


def apply_query_guardrails(tool_name: str, arguments: dict, question: str) -> dict:
    if tool_name not in ("query_odoo_search", "query_odoo_group", "query_odoo_count"):
        return arguments
    if not isinstance(arguments, dict):
        return arguments

    payload = dict(arguments)
    q = _normalize_text(question)
    model = payload.get("model")
    domain = list(payload.get("domain") or [])

    inferred_model = _infer_model_from_question(question)
    if inferred_model and (not model or model in ("sale.order", "purchase.order", "account.move")):
        model = inferred_model
        payload["model"] = inferred_model

    has_sales_terms = _contains_any(q, ["venta", "ventas", "pedido", "pedidos", "orden de venta", "ordenes de venta"])
    has_invoice_terms = _contains_any(q, ["factura", "facturas", "comprobante", "comprobantes", "emitida", "emitidas"])
    has_pending_terms = _contains_any(q, ["pendiente", "pendientes"])

    # Regla de negocio: "ventas pendientes" no debe derivar a account.move
    # salvo que el usuario hable explícitamente de facturas.
    if has_sales_terms and has_pending_terms and not has_invoice_terms:
        model = "sale.order"
        payload["model"] = "sale.order"

    period = detect_period_range(question)
    date_field = _date_field_for_model(model) if model else None
    if period and date_field:
        start, end = period
        domain = _strip_domain_clauses(domain, {date_field}, {">", ">=", "<", "<=", "="})
        domain = append_domain(domain, [[date_field, ">=", str(start)], [date_field, "<=", str(end)]])

    min_amount = _extract_min_amount(question)
    if min_amount is not None and model in ("sale.order", "purchase.order", "account.move"):
        domain = _strip_domain_clauses(domain, {"amount_total"}, {">", ">=", "<", "<=", "="})
        domain = append_domain(domain, [["amount_total", ">=", min_amount]])

    if model == "purchase.order" and _contains_any(q, ["compra", "compras", "proveedor", "orden de compra", "ordenes de compra"]):
        if not _has_domain_clause(domain, "state"):
            domain = append_domain(domain, [["state", "in", ["purchase", "done"]]])

    if model == "sale.order" and _contains_any(q, ["venta", "ventas", "pedido", "pedidos", "vendedor"]):
        if not _has_domain_clause(domain, "state"):
            if has_pending_terms:
                domain = append_domain(domain, [["state", "in", ["draft", "sent"]]])
            else:
                domain = append_domain(domain, [["state", "in", ["sale", "done"]]])

    if model == "account.move" and not _has_domain_clause(domain, "move_type"):
        if _contains_any(q, ["compra", "compras", "proveedor", "orden de compra"]):
            domain = append_domain(domain, [["move_type", "in", ["in_invoice", "in_refund"]]])
        elif _contains_any(q, ["venta", "ventas", "cliente", "clientes", "cobro", "cobros", "factura", "facturas", "emitida", "emitidas"]):
            domain = append_domain(domain, [["move_type", "in", ["out_invoice", "out_refund"]]])

    # Regla de negocio: "emitida/publicada" implica documento posteado.
    if model == "account.move" and _contains_any(q, ["emitida", "emitidas", "publicada", "publicadas"]):
        if not _has_domain_clause(domain, "state"):
            domain = append_domain(domain, [["state", "=", "posted"]])

    if (
        tool_name == "query_odoo_search"
        and date_field
        and not payload.get("orderby")
        and _contains_any(q, ["ultimo", "ultimos", "ultimas", "reciente", "recientes"])
    ):
        payload["orderby"] = f"{date_field} desc"

    payload["domain"] = _dedupe_domain(domain)
    return payload


def _dedupe_domain(domain):
    seen = set()
    result = []
    for clause in domain:
        if isinstance(clause, (list, tuple)):
            def _freeze(value):
                if isinstance(value, list):
                    return tuple(_freeze(v) for v in value)
                if isinstance(value, tuple):
                    return tuple(_freeze(v) for v in value)
                if isinstance(value, dict):
                    return tuple(sorted((k, _freeze(v)) for k, v in value.items()))
                return value
            key = _freeze(clause)
        else:
            key = clause
        if key in seen:
            continue
        seen.add(key)
        result.append(clause)
    return result
