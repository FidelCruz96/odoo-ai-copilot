from __future__ import annotations

from datetime import date, timedelta
import unicodedata

from .defaults import detect_period_range
from .intent_catalog import INTENT_CATALOG


MODEL_BUSINESS_OBJECT = {
    "sale.order": "sale_order",
    "sale.order.line": "sale_order_line",
    "purchase.order": "purchase_order",
    "purchase.order.line": "purchase_order_line",
    "account.move": "invoice",
    "res.partner": "partner",
    "product.product": "product",
    "stock.picking": "picking",
}

COUNT_TERMS = ("cuantos", "cuántos", "cuantas", "cuántas", "cantidad", "numero", "número", "total", "conteo")
LIST_TERMS = ("muestra", "muestrame", "muéstrame", "lista", "listar", "detalle", "ver", "dame")
RANGE_OPERATORS = {">", ">=", "<", "<=", "="}
DATETIME_RANGE_FIELDS = {
    ("sale.order", "date_order"),
    ("purchase.order", "date_order"),
    ("purchase.order", "date_approve"),
    ("stock.picking", "scheduled_date"),
}

INTENT_VARIANTS = {
    "count_facturas_pendientes": {"list": "list_facturas_pendientes"},
    "list_facturas_pendientes": {"count": "count_facturas_pendientes"},
}


def _normalize_text(text: str) -> str:
    text = (text or "").lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


def _contains_any(text: str, terms: tuple[str, ...] | list[str]) -> bool:
    return any(term in text for term in terms)


def _append_domain(domain: list, clause: list):
    if clause not in domain:
        domain.append(clause)


def _has_domain_clause(domain: list, field_name: str) -> bool:
    for clause in domain or []:
        if isinstance(clause, (list, tuple)) and len(clause) == 3 and clause[0] == field_name:
            return True
    return False


def _strip_domain_range(domain: list, field_name: str) -> list:
    output = []
    for clause in domain or []:
        if isinstance(clause, (list, tuple)) and len(clause) == 3:
            field, operator, _value = clause
            if field == field_name and operator in RANGE_OPERATORS:
                continue
        output.append(clause)
    return output


def _append_time_range(domain: list, model: str, field_name: str, start: str | None, end: str | None) -> list:
    normalized = _strip_domain_range(domain, field_name)
    if (model, field_name) in DATETIME_RANGE_FIELDS:
        if start:
            _append_domain(normalized, [field_name, ">=", f"{start} 00:00:00"])
        if end:
            try:
                next_day = str(date.fromisoformat(str(end)) + timedelta(days=1))
            except Exception:
                next_day = str(end)
            _append_domain(normalized, [field_name, "<", f"{next_day} 00:00:00"])
        return normalized

    if start:
        _append_domain(normalized, [field_name, ">=", start])
    if end:
        _append_domain(normalized, [field_name, "<=", end])
    return normalized


def infer_action(question: str, intent_name: str | None = None) -> str | None:
    q = _normalize_text(question)
    if _contains_any(q, COUNT_TERMS):
        return "count"
    if _contains_any(q, LIST_TERMS):
        return "list"

    spec = INTENT_CATALOG.get(intent_name) if intent_name else None
    if not spec:
        return None
    if spec.operation == "count":
        return "count"
    if spec.operation == "search_read":
        return "list"
    return "aggregate"


def _build_time_range(question: str, entities: dict | None = None):
    if isinstance(entities, dict) and entities.get("date_start") and entities.get("date_end"):
        return {"from": entities["date_start"], "to": entities["date_end"]}

    period = detect_period_range(question)
    if period:
        start, end = period
        return {"from": str(start), "to": str(end)}
    return None


def _infer_model_from_question(question: str) -> str | None:
    q = _normalize_text(question)
    if "factura" in q or "comprobante" in q:
        return "account.move"
    if "picking" in q or "pickings" in q or "recepcion" in q or "recepción" in q:
        return "stock.picking"
    if "compra" in q or "proveedor" in q:
        return "purchase.order"
    if "venta" in q or "pedido" in q:
        return "sale.order"
    return None


def build_semantic_frame(
    question: str,
    intent_name: str | None = None,
    entities: dict | None = None,
) -> dict:
    spec = INTENT_CATALOG.get(intent_name) if intent_name else None
    model = spec.model if spec else _infer_model_from_question(question)
    action = infer_action(question, intent_name=intent_name)
    time_range = _build_time_range(question, entities)

    frame = {
        "business_object": MODEL_BUSINESS_OBJECT.get(model),
        "model": model,
        "action": action,
        "time_range": time_range,
        "ordering": None,
        "limit": None,
        "filters": {},
        "groupby": [],
        "metric": None,
    }

    if spec:
        if spec.orderby:
            parts = spec.orderby.split()
            if len(parts) >= 2:
                frame["ordering"] = {"field": parts[0], "direction": parts[1]}
        frame["limit"] = entities.get("top_n", spec.limit_default) if isinstance(entities, dict) else spec.limit_default
        frame["groupby"] = list(spec.groupby or [])
        if spec.measure_field:
            frame["metric"] = "__count" if spec.measure_field == "__count" else f"{spec.measure_field}:sum"

    q = _normalize_text(question)
    if frame["model"] == "account.move":
        frame["filters"]["move_type"] = "out_invoice"
        if _contains_any(q, ("emitida", "emitidas", "emitio", "emitieron", "publicada", "publicadas")):
            frame["filters"]["state"] = "posted"
            frame["filters"]["document_status"] = "issued"
        if _contains_any(q, ("pendiente", "pendientes", "no pagada", "no pagadas")):
            frame["filters"]["state"] = "posted"
            frame["filters"]["payment_state"] = ["not_paid", "partial"]

    return frame


def resolve_intent_variant(intent_name: str | None, frame: dict | None) -> str | None:
    if not intent_name:
        return intent_name
    action = frame.get("action") if isinstance(frame, dict) else None
    variants = INTENT_VARIANTS.get(intent_name, {})
    return variants.get(action, intent_name)


def apply_frame_to_plan(plan: dict | None, frame: dict | None) -> dict | None:
    if not isinstance(plan, dict):
        return plan
    if not isinstance(frame, dict):
        return plan

    adjusted = dict(plan)
    arguments = dict(adjusted.get("arguments") or {})
    domain = list(arguments.get("domain") or [])
    model = arguments.get("model")
    filters = frame.get("filters") if isinstance(frame.get("filters"), dict) else {}

    if model == "account.move":
        move_type = filters.get("move_type")
        if move_type:
            _append_domain(domain, ["move_type", "=", move_type])

        state = filters.get("state")
        if state:
            _append_domain(domain, ["state", "=", state])

        payment_state = filters.get("payment_state")
        if isinstance(payment_state, list) and payment_state:
            _append_domain(domain, ["payment_state", "in", payment_state])

    time_range = frame.get("time_range") if isinstance(frame.get("time_range"), dict) else None
    if isinstance(time_range, dict):
        start = time_range.get("from")
        end = time_range.get("to")
        if model == "sale.order":
            domain = _append_time_range(domain, model, "date_order", start, end)
        elif model == "purchase.order":
            # Si el intent ya usa date_approve, respetamos ese campo y evitamos mezclar con date_order.
            if _has_domain_clause(domain, "date_approve"):
                domain = _append_time_range(domain, model, "date_approve", start, end)
            else:
                domain = _append_time_range(domain, model, "date_order", start, end)
        elif model == "account.move":
            domain = _append_time_range(domain, model, "invoice_date", start, end)
        elif model == "stock.picking":
            domain = _append_time_range(domain, model, "scheduled_date", start, end)

    arguments["domain"] = domain

    ordering = frame.get("ordering")
    if isinstance(ordering, dict) and adjusted.get("tool") in ("query_odoo_search", "query_odoo_group"):
        field = ordering.get("field")
        direction = ordering.get("direction")
        if field and direction and not arguments.get("orderby"):
            arguments["orderby"] = f"{field} {direction}"

    limit = frame.get("limit")
    if adjusted.get("tool") in ("query_odoo_search", "query_odoo_group") and isinstance(limit, int) and limit > 0:
        if not arguments.get("limit"):
            arguments["limit"] = limit

    adjusted["arguments"] = arguments
    return adjusted
