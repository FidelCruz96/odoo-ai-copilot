import json
import logging
import os
import time
import re
import uuid
from datetime import date, timedelta

from .execution.tool_executor import execute_tool
from .clarification_resolver import CLARIFICATION_RULES, detect_clarification_needed, resolve_pending_clarification
from .agent_rules import get_explicit_doc_regex, get_entity_hint_tokens, get_invoice_scope_patterns
from .intents.intent_matcher import detect_intent, detect_intent_family, detect_catalog_intent
from .intents.planner import build_entities, build_intent_plan
from .intents.semantic_frame import build_semantic_frame, resolve_intent_variant, apply_frame_to_plan
from .intents.defaults import apply_intent_defaults
from .memory_store import (
    get_last_entity,
    get_session_memory,
    set_pending_clarification,
    update_last_entity,
    set_last_ui_entity,
)
from .prompt_builder import build_date_context_prompt, compress_context, family_prompt_path, load_prompt
from .reference_resolver import resolve_followup, needs_followup_clarification
from .routes import AgentRoute
from .tool_loop import ToolLoopCallbacks, run_tool_guided_loop
from .tracing import log_agent_event
from .validators.semantic_validator import validate_plan_semantics
from .metrics.telemetry import evaluate_metrics, update_metrics_from_tool, update_quality_metrics_from_tool_result

logger = logging.getLogger(__name__)

DEFAULT_MAX_HISTORY = int(os.getenv("AI_CHAT_HISTORY_LIMIT", "8"))
LLM_COST_INPUT_PER_1K = float(os.getenv("LLM_COST_INPUT_PER_1K", "0"))
LLM_COST_OUTPUT_PER_1K = float(os.getenv("LLM_COST_OUTPUT_PER_1K", "0"))

EXPLICIT_DOC_RE = get_explicit_doc_regex()


def _query_has_explicit_entity_hint(question: str) -> bool:
    if not isinstance(question, str) or not question.strip():
        return False
    if EXPLICIT_DOC_RE.search(question):
        return True
    q = question.lower()
    hint_tokens = get_entity_hint_tokens()
    return any(token in q for token in hint_tokens) and any(ch.isdigit() for ch in question)


def _context_ui_entity(context: dict | None):
    if not isinstance(context, dict):
        return None
    client = context.get("client")
    if not isinstance(client, dict):
        return None
    model = client.get("active_model")
    raw_id = client.get("active_id")
    if not model:
        return None
    try:
        entity_id = int(raw_id)
    except Exception:
        return None
    if entity_id <= 0:
        return None
    return {
        "model": str(model),
        "id": entity_id,
        "display_name": f"{model} #{entity_id}",
        "fields": {},
    }


def _dedupe_keep_order(values):
    seen = set()
    result = []
    for v in values:
        if v not in seen:
            result.append(v)
            seen.add(v)
    return result


def _detect_avg_group_intent(question: str):
    q = (question or "").lower()

    has_avg = any(x in q for x in ["promedio", "promedio de", "media", "average", "avg"])
    if not has_avg:
        return None

    if "cliente" in q or "clientes" in q:
        return {"entity": "partner_id", "label": "cliente"}
    if "vendedor" in q or "vendedores" in q or "usuario" in q:
        return {"entity": "user_id", "label": "vendedor"}
    if "proveedor" in q or "proveedores" in q:
        return {"entity": "partner_id", "label": "proveedor"}
    if "producto" in q or "productos" in q:
        return {"entity": "product_id", "label": "producto"}

    return None


def _compute_avg_from_group_rows(rows, entity_field: str, value_field: str = "amount_total"):
    if not isinstance(rows, list):
        return None

    valid_rows = []
    total_value = 0.0

    for row in rows:
        if not isinstance(row, dict):
            continue

        entity_val = row.get(entity_field)
        if entity_val in (False, None, [], ()):
            continue

        value = row.get(value_field, 0.0)
        try:
            value = float(value or 0.0)
        except Exception:
            value = 0.0

        valid_rows.append(row)
        total_value += value

    group_count = len(valid_rows)
    if group_count == 0:
        return {"group_count": 0, "total_value": 0.0, "average_value": 0.0}

    return {
        "group_count": group_count,
        "total_value": round(total_value, 2),
        "average_value": round(total_value / group_count, 2),
    }


def _normalize_read_group_args(arguments: dict, question: str):
    if not isinstance(arguments, dict):
        return arguments

    avg_group_intent = _detect_avg_group_intent(question)
    if not avg_group_intent:
        return arguments

    raw_fields = list(arguments.get("fields") or [])
    groupby = [g for g in (arguments.get("groupby") or []) if isinstance(g, str) and g.strip()]
    domain = list(arguments.get("domain") or [])

    model = arguments.get("model")
    entity_field = avg_group_intent["entity"]

    if not groupby:
        groupby = [entity_field]

    cleaned_fields = []
    for g in groupby:
        cleaned_fields.append(g)

    if model in ("sale.order", "purchase.order"):
        cleaned_fields.append("amount_total:sum")
    elif model == "sale.order.line":
        cleaned_fields.append("product_uom_qty:sum")
    elif model == "purchase.order.line":
        cleaned_fields.append("product_qty:sum")

    arguments["fields"] = _dedupe_keep_order(cleaned_fields)
    arguments["groupby"] = groupby
    arguments["domain"] = domain
    arguments["orderby"] = ""
    arguments["limit"] = None
    return arguments


def _extract_partner_ids_from_domain(domain):
    ids = []
    if not isinstance(domain, list):
        return ids
    for clause in domain:
        if isinstance(clause, (list, tuple)) and len(clause) == 3:
            field, op, val = clause
            if field == "partner_id":
                if op == "=" and isinstance(val, int):
                    ids.append(val)
                elif op == "in" and isinstance(val, list):
                    ids.extend([v for v in val if isinstance(v, int)])
    return ids


def _extract_ids_from_domain(domain):
    pairs = []
    if not isinstance(domain, list):
        return pairs
    for clause in domain:
        if isinstance(clause, (list, tuple)) and len(clause) == 3:
            field, op, val = clause
            if op == "=" and isinstance(val, int):
                pairs.append((field, [val]))
            elif op == "in" and isinstance(val, list):
                ids = [v for v in val if isinstance(v, int)]
                if ids:
                    pairs.append((field, ids))
    return pairs


def _is_count_question(text: str) -> bool:
    if not text:
        return False
    q = text.lower()
    return any(k in q for k in ("cuantos", "cuántos", "cantidad", "numero", "número", "total"))


def _is_amount_followup(text: str) -> bool:
    if not text:
        return False
    q = text.lower()
    return any(k in q for k in ("monto", "importe", "total", "cuanto", "cuánto")) and any(
        k in q for k in ("cada uno", "cada", "esos", "esos clientes", "los mismos", "anteriores")
    )


def _is_data_question(text: str) -> bool:
    if not text:
        return False
    q = text.lower()
    return any(k in q for k in (
        "cuantos", "cuántos", "cantidad", "numero", "número", "total",
        "monto", "importe", "ventas", "compras", "lista", "top", "más", "mas"
    ))


def _extract_entity_from_tool_result(model: str, result, tool_name: str, arguments: dict | None = None):
    if not model:
        return None

    if tool_name == "query_odoo_group":
        groupby = arguments.get("groupby") if isinstance(arguments, dict) else []
        if groupby != ["id"]:
            return None

    if not isinstance(result, list) or not result:
        return None

    first = result[0]
    if not isinstance(first, dict):
        return None

    raw_id = first.get("id")
    if tool_name == "query_odoo_group" and isinstance(raw_id, list) and len(raw_id) >= 2:
        return {
            "model": model,
            "id": raw_id[0],
            "display_name": raw_id[1],
            "fields": {
                key: value for key, value in first.items()
                if key not in {"id", "__domain", "__context", "__fold"}
            },
        }

    if tool_name == "query_odoo_read" and isinstance(raw_id, int):
        return {
            "model": model,
            "id": raw_id,
            "display_name": first.get("name") or first.get("display_name"),
            "fields": {
                key: value for key, value in first.items()
                if key != "id"
            },
        }

    return None


def _extract_entity_from_search_result(model: str, result, arguments: dict | None = None):
    if not model or model not in {"sale.order", "purchase.order", "account.move", "res.partner"}:
        return None
    if not isinstance(result, list) or len(result) != 1 or not isinstance(result[0], int):
        return None
    args = arguments if isinstance(arguments, dict) else {}
    domain = args.get("domain")
    display_name = None
    if isinstance(domain, list):
        for clause in domain:
            if not (isinstance(clause, (list, tuple)) and len(clause) == 3):
                continue
            field, operator, value = clause
            if operator != "=":
                continue
            if field in ("name", "display_name", "invoice_origin", "ref") and isinstance(value, str) and value.strip():
                display_name = value.strip()
                break
    if not display_name:
        display_name = f"ID {result[0]}"
    return {
        "model": model,
        "id": result[0],
        "display_name": display_name,
        "fields": {"name": display_name},
    }


def _hydrate_entity_display_name(entity: dict | None) -> dict | None:
    if not isinstance(entity, dict):
        return entity
    model = entity.get("model")
    entity_id = entity.get("id")
    if not isinstance(model, str) or not isinstance(entity_id, int):
        return entity

    current_name = entity.get("display_name")
    if isinstance(current_name, str) and current_name.strip() and not current_name.strip().lower().startswith("id "):
        return entity

    try:
        read_result = execute_tool(
            "query_odoo_read",
            {"model": model, "ids": [entity_id], "fields": ["name", "display_name", "ref", "invoice_origin"]},
        )
    except Exception:
        return entity

    if not isinstance(read_result, list) or not read_result:
        return entity
    row = read_result[0]
    if not isinstance(row, dict):
        return entity

    resolved_name = row.get("name") or row.get("display_name") or row.get("ref") or row.get("invoice_origin")
    if not (isinstance(resolved_name, str) and resolved_name.strip()):
        return entity

    output = dict(entity)
    output["display_name"] = resolved_name.strip()
    fields = dict(output.get("fields") or {})
    fields.update({k: v for k, v in row.items() if k != "id"})
    output["fields"] = fields
    return output


def _strip_domain_field(domain: list | None, field_name: str) -> list:
    rows = []
    for clause in domain or []:
        if isinstance(clause, (list, tuple)) and len(clause) == 3 and clause[0] == field_name:
            continue
        rows.append(clause)
    return rows


def _dedupe_domain_rows(domain: list | None) -> list:
    if not isinstance(domain, list):
        return []
    out = []
    seen = set()
    for clause in domain:
        try:
            key = json.dumps(clause, ensure_ascii=False, sort_keys=True)
        except Exception:
            key = str(clause)
        if key in seen:
            continue
        seen.add(key)
        out.append(clause)
    return out


def _looks_like_generic_context_name(value: str | None, source_model: str | None = None, source_id: int | None = None) -> bool:
    if not isinstance(value, str):
        return True
    text = value.strip()
    if not text:
        return True
    lower = text.lower()
    if lower.startswith("id "):
        return True
    if isinstance(source_model, str) and isinstance(source_id, int):
        if lower == f"{source_model.lower()} #{source_id}":
            return True
    return False


def _resolve_related_source_name(plan: dict, metrics: dict) -> str | None:
    source_model = plan.get("source_model")
    source_id = plan.get("source_id")
    source_display_name = plan.get("source_display_name")

    if not isinstance(source_model, str) or not isinstance(source_id, int):
        return source_display_name if isinstance(source_display_name, str) else None

    if isinstance(source_display_name, str) and source_display_name.strip():
        if not _looks_like_generic_context_name(source_display_name, source_model, source_id):
            return source_display_name.strip()

    read_args = {
        "model": source_model,
        "ids": [source_id],
        "fields": ["name"],
    }
    update_metrics_from_tool(metrics, "query_odoo_read", read_args)
    metrics["tool_calls"] += 1
    metrics["tools_used"].append("query_odoo_read")
    read_result = execute_tool("query_odoo_read", read_args)
    update_quality_metrics_from_tool_result(metrics, "query_odoo_read", read_args, read_result)
    if isinstance(read_result, list) and read_result:
        row = read_result[0]
        if isinstance(row, dict):
            resolved_name = row.get("name")
            if isinstance(resolved_name, str) and resolved_name.strip():
                return resolved_name.strip()

    if isinstance(source_display_name, str) and source_display_name.strip():
        return source_display_name.strip()
    return None


def _default_read_fields_for_model(model_name: str | None) -> list[str]:
    mapping = {
        "sale.order": ["name", "partner_id", "date_order", "amount_total", "state"],
        "purchase.order": ["name", "partner_id", "date_order", "amount_total", "state"],
        "account.move": ["name", "partner_id", "invoice_date", "amount_total", "state", "move_type"],
        "sale.order.line": ["product_id", "product_uom_qty", "price_unit", "price_subtotal"],
        "purchase.order.line": ["product_id", "product_qty", "price_unit", "price_subtotal"],
        "res.partner": ["name", "email", "phone", "mobile", "vat"],
    }
    return list(mapping.get(model_name, ["name"]))


def _normalize_read_fields_with_schema(arguments: dict, model_info: dict | None) -> dict:
    if not isinstance(arguments, dict):
        return arguments
    payload = dict(arguments)
    model_name = payload.get("model")
    model_fields = (model_info or {}).get("fields") if isinstance(model_info, dict) else {}
    model_fields = model_fields if isinstance(model_fields, dict) else {}

    def _is_valid(field_name: str) -> bool:
        if not isinstance(field_name, str):
            return False
        base = field_name.split(":", 1)[0].strip()
        if not base:
            return False
        if not model_fields:
            return ":" not in field_name
        return base in model_fields and ":" not in field_name

    raw_fields = payload.get("fields")
    normalized = []
    if isinstance(raw_fields, list) and raw_fields:
        for field_name in raw_fields:
            if not _is_valid(field_name):
                continue
            base = field_name.split(":", 1)[0].strip()
            if base not in normalized:
                normalized.append(base)

    if not normalized:
        for field_name in _default_read_fields_for_model(model_name):
            if _is_valid(field_name):
                base = field_name.split(":", 1)[0].strip()
                if base not in normalized:
                    normalized.append(base)

    payload["fields"] = normalized or ["name"]
    return payload


def _pick_invoice_source_entity(memory: dict | None):
    if not isinstance(memory, dict):
        return None
    for key in ("last_explicit_entity", "primary_entity", "last_ui_entity", "last_inferred_entity", "last_entity"):
        entity = memory.get(key)
        if not isinstance(entity, dict):
            continue
        model = entity.get("model")
        entity_id = entity.get("id")
        if model in ("sale.order", "purchase.order") and isinstance(entity_id, int):
            return entity
    return None


def _is_entity_scoped_invoice_query(question: str) -> bool:
    q = (question or "").lower()
    if _query_has_explicit_entity_hint(question):
        return True
    scoped_patterns = get_invoice_scope_patterns()
    return any(pattern in q for pattern in scoped_patterns)


def _enforce_invoice_semantics(arguments: dict, question: str, memory: dict | None, tool_name: str, model_info: dict | None):
    if not isinstance(arguments, dict):
        return arguments
    if tool_name not in ("query_odoo_search", "query_odoo_group", "query_odoo_count"):
        return arguments
    if arguments.get("model") != "account.move":
        return arguments

    payload = dict(arguments)
    domain = list(payload.get("domain") or [])
    q = (question or "").lower()
    if not any(token in q for token in ("factura", "facturas", "comprobante", "comprobantes", "invoice")):
        return payload

    source_entity = _pick_invoice_source_entity(memory)
    if source_entity and _is_entity_scoped_invoice_query(question):
        source_model = source_entity.get("model")
        source_name = source_entity.get("display_name")
        if not isinstance(source_name, str) or not source_name.strip():
            fields = source_entity.get("fields")
            if isinstance(fields, dict):
                source_name = fields.get("name")
        if isinstance(source_name, str) and source_name.strip():
            domain = _strip_domain_field(domain, "invoice_origin")
            domain.append(["invoice_origin", "=", source_name.strip()])

        move_types = None
        if source_model == "purchase.order":
            move_types = ["in_invoice", "in_refund"]
        elif source_model == "sale.order":
            move_types = ["out_invoice", "out_refund"]
        if move_types:
            domain = _strip_domain_field(domain, "move_type")
            domain.append(["move_type", "in", move_types])

    model_fields = (model_info or {}).get("fields") if isinstance(model_info, dict) else {}
    model_fields = model_fields if isinstance(model_fields, dict) else {}
    if model_fields:
        cleaned = []
        for clause in domain:
            if not (isinstance(clause, (list, tuple)) and len(clause) == 3):
                cleaned.append(clause)
                continue
            field_name = clause[0]
            if isinstance(field_name, str) and field_name.split(".", 1)[0] not in model_fields:
                continue
            cleaned.append(clause)
        domain = cleaned

    payload["domain"] = _dedupe_domain_rows(domain)
    return payload


def _clear_resolved_entity_conflicts(memory: dict | None, selected_entity: dict | None) -> dict:
    payload = dict(memory) if isinstance(memory, dict) else {}
    if not isinstance(selected_entity, dict):
        return payload
    selected_model = selected_entity.get("model")
    selected_id = selected_entity.get("id")
    if not selected_model or not isinstance(selected_id, int):
        return payload

    last_inferred = payload.get("last_inferred_entity")
    if isinstance(last_inferred, dict):
        if last_inferred.get("model") != selected_model:
            payload.pop("last_inferred_entity", None)

    secondary = payload.get("secondary_entity")
    if isinstance(secondary, dict):
        if secondary.get("model") in ("sale.order", "purchase.order", "account.move") and secondary.get("model") != selected_model:
            payload.pop("secondary_entity", None)

    recent = payload.get("recent_entities")
    if isinstance(recent, list):
        filtered = []
        for row in recent:
            if not isinstance(row, dict):
                continue
            model = row.get("model")
            if model == selected_model:
                filtered.append(row)
        if not filtered:
            filtered = [{"model": selected_model, "id": selected_id, "display_name": selected_entity.get("display_name")}]
        payload["recent_entities"] = filtered[-5:]
    return payload


def _followup_read_fields(model: str):
    fields_by_model = {
        "purchase.order": ["name", "partner_id", "date_order", "amount_total", "state"],
        "sale.order": ["name", "partner_id", "date_order", "amount_total", "state"],
        "account.move": ["name", "partner_id", "invoice_date", "amount_total", "state", "move_type"],
        "res.partner": ["name", "email", "phone", "mobile", "vat"],
    }
    return fields_by_model.get(model, ["name"])


def _format_followup_answer(model: str, row: dict, fallback_display_name: str | None = None):
    if not isinstance(row, dict):
        return "No encontré el registro solicitado."

    identifier = row.get("name") or row.get("display_name") or fallback_display_name or f"ID {row.get('id')}"

    if model == "purchase.order":
        partner = row.get("partner_id")
        partner_name = partner[1] if isinstance(partner, (list, tuple)) and len(partner) >= 2 else None
        parts = [f"La compra es {identifier}."]
        if partner_name:
            parts.append(f"Proveedor: {partner_name}.")
        if row.get("date_order"):
            parts.append(f"Fecha: {row['date_order']}.")
        if row.get("amount_total") is not None:
            parts.append(f"Monto total: {row['amount_total']}.")
        if row.get("state"):
            parts.append(f"Estado: {row['state']}.")
        return " ".join(parts)

    if model == "sale.order":
        partner = row.get("partner_id")
        partner_name = partner[1] if isinstance(partner, (list, tuple)) and len(partner) >= 2 else None
        parts = [f"El pedido es {identifier}."]
        if partner_name:
            parts.append(f"Cliente: {partner_name}.")
        if row.get("date_order"):
            parts.append(f"Fecha: {row['date_order']}.")
        if row.get("amount_total") is not None:
            parts.append(f"Monto total: {row['amount_total']}.")
        if row.get("state"):
            parts.append(f"Estado: {row['state']}.")
        return " ".join(parts)

    if model == "account.move":
        partner = row.get("partner_id")
        partner_name = partner[1] if isinstance(partner, (list, tuple)) and len(partner) >= 2 else None
        parts = [f"El documento es {identifier}."]
        if partner_name:
            parts.append(f"Contacto: {partner_name}.")
        if row.get("invoice_date"):
            parts.append(f"Fecha: {row['invoice_date']}.")
        if row.get("amount_total") is not None:
            parts.append(f"Monto total: {row['amount_total']}.")
        if row.get("state"):
            parts.append(f"Estado: {row['state']}.")
        return " ".join(parts)

    return f"El registro es {identifier}."


def _format_related_followup_answer(plan: dict, rows):
    intent = plan.get("intent")
    source_label = plan.get("source_display_name") or f"ID {plan.get('source_id')}"

    if intent == "products":
        if not isinstance(rows, list) or not rows:
            return f"No encontré productos relacionados con {source_label}."

        lines = [f"Productos de {source_label}:"]
        for index, row in enumerate(rows[:10], start=1):
            product = row.get("product_id")
            product_name = product[1] if isinstance(product, (list, tuple)) and len(product) >= 2 else "Sin producto"
            qty = row.get("product_uom_qty", row.get("product_qty"))
            subtotal = row.get("price_subtotal")
            parts = [f"{index}. {product_name}"]
            if qty is not None:
                parts.append(f"cantidad {qty}")
            if subtotal is not None:
                parts.append(f"subtotal {subtotal}")
            lines.append(" - ".join(parts))
        return "\n".join(lines)

    if intent == "invoices":
        if not isinstance(rows, list) or not rows:
            return f"{source_label} no tiene facturas asociadas."

        header = f"{source_label} tiene {len(rows)} factura(s) asociada(s):"
        lines = [header]
        for index, row in enumerate(rows[:10], start=1):
            name = row.get("name") or f"ID {row.get('id')}"
            invoice_date = row.get("invoice_date") or "sin fecha"
            amount = row.get("amount_total")
            state = row.get("state")
            parts = [f"{index}. {name}", f"fecha {invoice_date}"]
            if amount is not None:
                parts.append(f"monto {amount}")
            if state:
                parts.append(f"estado {state}")
            lines.append(" - ".join(parts))
        return "\n".join(lines)

    if intent == "related_sales":
        if not isinstance(rows, list) or not rows:
            return f"No encontré ventas relacionadas con {source_label}."

        lines = [f"Ventas relacionadas con {source_label}:"]
        for index, row in enumerate(rows[:10], start=1):
            name = row.get("name") or f"ID {row.get('id')}"
            partner = row.get("partner_id")
            partner_name = partner[1] if isinstance(partner, (list, tuple)) and len(partner) >= 2 else "-"
            date_value = row.get("date_order") or "-"
            amount = row.get("amount_total", "-")
            state = row.get("state", "-")
            lines.append(
                f"{index}. {name} | Cliente: {partner_name} | Fecha: {date_value} | Monto: {amount} | Estado: {state}"
            )
        return "\n".join(lines)

    return "No encontré información relacionada."


def _execute_related_followup(plan: dict, question: str, metrics: dict):
    search_plan = plan.get("search") or {}
    intent = plan.get("intent")
    source_model = plan.get("source_model")
    domain = list(search_plan.get("domain") or [])

    if intent in ("invoices", "related_sales"):
        source_name = _resolve_related_source_name(plan, metrics)
        if isinstance(source_name, str) and source_name.strip():
            plan["source_display_name"] = source_name.strip()
            if intent == "invoices":
                domain = _strip_domain_field(domain, "invoice_origin")
                domain.append(["invoice_origin", "=", source_name.strip()])
                if source_model == "purchase.order":
                    domain = _strip_domain_field(domain, "move_type")
                    domain.append(["move_type", "in", ["in_invoice", "in_refund"]])
                elif source_model == "sale.order":
                    domain = _strip_domain_field(domain, "move_type")
                    domain.append(["move_type", "in", ["out_invoice", "out_refund"]])
            elif intent == "related_sales":
                domain = _strip_domain_field(domain, "rt_purchase_order")
                domain.append(["rt_purchase_order", "=", source_name.strip()])

    search_args = {
        "model": search_plan.get("model"),
        "domain": _dedupe_domain_rows(domain),
    }
    update_metrics_from_tool(metrics, "query_odoo_search", search_args)
    metrics["tool_calls"] += 1
    metrics["tools_used"].append("query_odoo_search")
    search_result = execute_tool("query_odoo_search", search_args)
    update_quality_metrics_from_tool_result(metrics, "query_odoo_search", search_args, search_result)
    if isinstance(search_result, dict) and "error" in search_result:
        return None, "related_followup_search_error"

    ids = search_result if isinstance(search_result, list) else []
    if not ids:
        return _format_related_followup_answer(plan, []), None

    read_plan = plan.get("read") or {}
    read_args = {
        "model": read_plan.get("model"),
        "ids": ids,
        "fields": read_plan.get("fields") or [],
    }
    update_metrics_from_tool(metrics, "query_odoo_read", read_args)
    metrics["tool_calls"] += 1
    metrics["tools_used"].append("query_odoo_read")
    read_result = execute_tool("query_odoo_read", read_args)
    update_quality_metrics_from_tool_result(metrics, "query_odoo_read", read_args, read_result)
    if isinstance(read_result, dict) and "error" in read_result:
        return None, "related_followup_read_error"

    return _format_related_followup_answer(plan, read_result), None


def _try_deterministic_path(question: str):
    intent_name, confidence = detect_catalog_intent(question)
    if not intent_name or confidence < 0.72:
        return None

    entities = build_entities(question)
    semantic_frame = build_semantic_frame(question, intent_name=intent_name, entities=entities)

    effective_intent_name = resolve_intent_variant(intent_name, semantic_frame) or intent_name
    if effective_intent_name != intent_name:
        intent_name = effective_intent_name
        semantic_frame = build_semantic_frame(question, intent_name=intent_name, entities=entities)

    plan = build_intent_plan(intent_name, entities)
    if not plan:
        return None
    plan = apply_frame_to_plan(plan, semantic_frame)

    tool_name = plan["tool"]
    arguments = plan["arguments"]

    semantic_error = validate_plan_semantics(intent_name, tool_name, arguments)
    if semantic_error:
        logger.warning("Deterministic semantic error: %s", semantic_error)
        return None

    return {
        "intent": intent_name,
        "confidence": confidence,
        "plan": plan,
        "semantic_frame": semantic_frame,
    }


def _resolve_preferred_group_metrics(arguments: dict | None) -> list[str]:
    if not isinstance(arguments, dict):
        return []

    preferred: list[str] = []
    groupby = arguments.get("groupby") or []
    fields = arguments.get("fields") or []
    orderby = arguments.get("orderby")

    if isinstance(orderby, str):
        token = orderby.strip().split()[0] if orderby.strip() else ""
        if token:
            preferred.append(token)

    for field_expr in fields:
        if not isinstance(field_expr, str):
            continue
        if field_expr == "__count":
            preferred.append("__count")
            continue
        if ":" in field_expr:
            base_field = field_expr.split(":", 1)[0]
            if base_field and base_field not in groupby:
                preferred.append(base_field)

    # Mantener orden y evitar duplicados.
    seen = set()
    output = []
    for item in preferred:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def _extract_read_group_metric(
    row: dict,
    groupby: list,
    preferred_fields: list[str] | None = None,
) -> tuple[str | None, float | int | None]:
    if not isinstance(row, dict):
        return None, None

    preferred_fields = preferred_fields or []

    for preferred in preferred_fields:
        if preferred == "__count":
            count_value = row.get("__count")
            if isinstance(count_value, (int, float)):
                return "__count", count_value
            # Fallback: algunos read_group devuelven <group_field>_count.
            for key, value in row.items():
                if key.endswith("_count") and isinstance(value, (int, float)):
                    return key, value
            continue

        value = row.get(preferred)
        if isinstance(value, (int, float)):
            return preferred, value

    for k, v in row.items():
        if k in (groupby or []):
            continue
        if k.startswith("__"):
            continue
        # Evita tomar campos automáticos *_count si hay métricas de negocio.
        if k.endswith("_count"):
            continue
        if isinstance(v, (int, float)):
            return k, v

    for k, v in row.items():
        if k.endswith("_count") and isinstance(v, (int, float)):
            return k, v

    return None, None


def _extract_group_label(row: dict, groupby: list) -> str:
    if not isinstance(row, dict):
        return "Sin etiqueta"
    if not groupby:
        return "Total"
    group_field = groupby[0]
    value = row.get(group_field)
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return str(value[1])
    if value is False or value is None:
        return "Sin etiqueta"
    return str(value)


def _human_metric_name(metric_name: str | None) -> str:
    mapping = {
        "__count": "cantidad",
        "amount_total": "monto",
        "product_uom_qty": "cantidad",
        "product_qty": "cantidad",
        "price_total": "monto",
    }
    if not metric_name:
        return "valor"
    return mapping.get(metric_name, metric_name)


def _format_read_group_rows(rows: list, groupby: list, preferred_metric_fields: list[str] | None = None) -> str:
    if not isinstance(rows, list) or not rows:
        return "No hay datos para ese criterio."

    if not groupby:
        metric_name, metric_value = _extract_read_group_metric(rows[0], groupby, preferred_fields=preferred_metric_fields)
        if metric_value is None:
            return "No hay datos."
        return f"Total ({_human_metric_name(metric_name)}): {metric_value}."

    if len(rows) == 1:
        return _format_read_group_answer(rows[0], groupby, preferred_metric_fields=preferred_metric_fields)

    lines = ["Resultados:"]
    for index, row in enumerate(rows[:10], start=1):
        label = _extract_group_label(row, groupby)
        metric_name, metric_value = _extract_read_group_metric(row, groupby, preferred_fields=preferred_metric_fields)
        if metric_value is None:
            lines.append(f"{index}. {label}")
            continue
        metric_label = _human_metric_name(metric_name)
        lines.append(f"{index}. {label} | {metric_label}: {metric_value}")
    return "\n".join(lines)



def _extract_group_count(row: dict, group_field: str) -> int:
    if not isinstance(row, dict):
        return 0
    raw = row.get("__count")
    if isinstance(raw, (int, float)):
        return int(raw)
    alias = f"{group_field}_count"
    raw = row.get(alias)
    if isinstance(raw, (int, float)):
        return int(raw)
    for key, value in row.items():
        if key.endswith("_count") and isinstance(value, (int, float)):
            return int(value)
    return 0


def _format_clientes_facturas_vencidas_ranking(rows: list) -> str:
    if not isinstance(rows, list) or not rows:
        return "No hay clientes con facturas vencidas para ese criterio."

    lines = ["Clientes con más facturas vencidas:"]
    for index, row in enumerate(rows[:10], start=1):
        label = _extract_group_label(row, ["partner_id"])
        count_value = _extract_group_count(row, "partner_id")
        pending_amount = row.get("amount_residual")
        if not isinstance(pending_amount, (int, float)):
            pending_amount = row.get("amount_total")
        lines.append(
            f"{index}. {label} | facturas vencidas: {count_value} | saldo pendiente: {pending_amount}"
        )
    return "\n".join(lines)


def _execute_operational_summary_today(arguments: dict, metrics: dict) -> str | None:
    if not isinstance(arguments, dict):
        return None

    today = arguments.get("today") or str(date.today())
    today_start = arguments.get("today_start") or f"{today} 00:00:00"
    tomorrow_start = arguments.get("tomorrow_start") or f"{date.today() + timedelta(days=1)} 00:00:00"

    query_plan = [
        (
            "ventas_confirmadas",
            {
                "model": "sale.order",
                "domain": [["state", "in", ["sale", "done"]], ["date_order", ">=", today_start], ["date_order", "<", tomorrow_start]],
            },
        ),
        (
            "facturas_pendientes",
            {
                "model": "account.move",
                "domain": [
                    ["move_type", "=", "out_invoice"],
                    ["state", "=", "posted"],
                    ["payment_state", "in", ["not_paid", "partial"]],
                ],
            },
        ),
        (
            "compras_por_recibir",
            {
                "model": "purchase.order",
                "domain": [["state", "in", ["purchase", "done"]], ["receipt_status", "not in", ["full", "2_received"]]],
            },
        ),
        (
            "pickings_por_validar",
            {
                "model": "stock.picking",
                "domain": [
                    ["state", "in", ["assigned", "waiting", "partially_available"]],
                    ["scheduled_date", ">=", today_start],
                    ["scheduled_date", "<", tomorrow_start],
                ],
            },
        ),
    ]

    values: dict[str, int] = {}
    for key, arguments_count in query_plan:
        update_metrics_from_tool(metrics, "query_odoo_count", arguments_count)
        metrics["tool_calls"] += 1
        metrics["tools_used"].append("query_odoo_count")
        result = execute_tool("query_odoo_count", arguments_count)
        update_quality_metrics_from_tool_result(metrics, "query_odoo_count", arguments_count, result)
        if isinstance(result, dict) and "error" in result:
            metrics["tool_success"] = False
            return None
        try:
            values[key] = int(result or 0)
        except Exception:
            values[key] = 0

    return (
        f"Resumen operativo de hoy ({today}):\n"
        f"- Ventas confirmadas hoy: {values.get('ventas_confirmadas', 0)}\n"
        f"- Facturas pendientes de cobro: {values.get('facturas_pendientes', 0)}\n"
        f"- Órdenes de compra por recibir: {values.get('compras_por_recibir', 0)}\n"
        f"- Pickings pendientes de validar: {values.get('pickings_por_validar', 0)}"
    )


def _execute_pickings_status_summary(arguments: dict, metrics: dict) -> str | None:
    _ = arguments  # flujo determinístico sin parámetros variables por ahora
    query_plan = [
        ("en_espera", {"model": "stock.picking", "domain": [["state", "=", "waiting"]]}),
        (
            "disponible",
            {"model": "stock.picking", "domain": [["state", "in", ["assigned", "partially_available"]]]},
        ),
        ("hecho", {"model": "stock.picking", "domain": [["state", "=", "done"]]}),
    ]

    values: dict[str, int] = {}
    for key, arguments_count in query_plan:
        update_metrics_from_tool(metrics, "query_odoo_count", arguments_count)
        metrics["tool_calls"] += 1
        metrics["tools_used"].append("query_odoo_count")
        result = execute_tool("query_odoo_count", arguments_count)
        update_quality_metrics_from_tool_result(metrics, "query_odoo_count", arguments_count, result)
        if isinstance(result, dict) and "error" in result:
            metrics["tool_success"] = False
            return None
        try:
            values[key] = int(result or 0)
        except Exception:
            values[key] = 0

    return (
        "Conteo de pickings por estado:\n"
        f"- En espera: {values.get('en_espera', 0)}\n"
        f"- Disponible: {values.get('disponible', 0)}\n"
        f"- Hecho: {values.get('hecho', 0)}"
    )

def _format_read_group_answer(row: dict, groupby: list, preferred_metric_fields: list[str] | None = None) -> str:
    if not isinstance(row, dict):
        return "No hay datos."
    label = None
    if groupby:
        g = groupby[0]
        val = row.get(g)
        if isinstance(val, (list, tuple)) and len(val) >= 2:
            label = val[1]
        elif val is not None:
            label = str(val)
    metric_name, metric_value = _extract_read_group_metric(row, groupby, preferred_fields=preferred_metric_fields)
    if label and metric_name and metric_value is not None:
        if metric_name == "__count":
            return f"{label} con {metric_value} pedidos."
        return f"{label} con {metric_value}."
    if metric_name and metric_value is not None:
        return f"{metric_name}: {metric_value}."
    return "No hay datos."


def _format_deterministic_read_answer(intent_name: str | None, model: str | None, rows) -> str:
    if not isinstance(rows, list) or not rows:
        return "No hay registros."

    if intent_name in ("list_facturas_pendientes", "list_facturas_emitidas_periodo"):
        header = (
            "Facturas pendientes:"
            if intent_name == "list_facturas_pendientes"
            else "Facturas emitidas:"
        )
        lines = [header]
        for index, row in enumerate(rows[:20], start=1):
            name = row.get("name") or f"ID {row.get('id')}"
            partner = row.get("partner_id")
            partner_name = partner[1] if isinstance(partner, (list, tuple)) and len(partner) >= 2 else "Sin cliente"
            invoice_date = row.get("invoice_date") or "sin fecha"
            amount = row.get("amount_total")
            state = row.get("state") or "-"
            payment_state = row.get("payment_state") or "-"
            lines.append(
                f"{index}. {name} | Cliente: {partner_name} | Fecha: {invoice_date} | "
                f"Monto: {amount} | Estado: {state} | Pago: {payment_state}"
            )
        return "\n".join(lines)

    if model == "sale.order":
        header = "Órdenes de venta encontradas:"
        lines = [header]
        for index, row in enumerate(rows[:20], start=1):
            name = row.get("name") or f"ID {row.get('id')}"
            partner = row.get("partner_id")
            partner_name = partner[1] if isinstance(partner, (list, tuple)) and len(partner) >= 2 else "Sin cliente"
            date_value = row.get("date_order") or "-"
            amount = row.get("amount_total", "-")
            state = row.get("state", "-")
            lines.append(
                f"{index}. {name} | Cliente: {partner_name} | Fecha: {date_value} | Monto: {amount} | Estado: {state}"
            )
        return "\n".join(lines)

    if model == "purchase.order":
        header = "Órdenes de compra encontradas:"
        lines = [header]
        for index, row in enumerate(rows[:20], start=1):
            name = row.get("name") or f"ID {row.get('id')}"
            partner = row.get("partner_id")
            partner_name = partner[1] if isinstance(partner, (list, tuple)) and len(partner) >= 2 else "Sin proveedor"
            date_value = row.get("date_order") or "-"
            amount = row.get("amount_total", "-")
            state = row.get("state", "-")
            lines.append(
                f"{index}. {name} | Proveedor: {partner_name} | Fecha: {date_value} | Monto: {amount} | Estado: {state}"
            )
        return "\n".join(lines)

    if model == "account.move":
        lines = ["Documentos encontrados:"]
        for index, row in enumerate(rows[:20], start=1):
            name = row.get("name") or f"ID {row.get('id')}"
            partner = row.get("partner_id")
            partner_name = partner[1] if isinstance(partner, (list, tuple)) and len(partner) >= 2 else "-"
            invoice_date = row.get("invoice_date") or "-"
            amount = row.get("amount_total", "-")
            state = row.get("state", "-")
            lines.append(
                f"{index}. {name} | Contacto: {partner_name} | Fecha: {invoice_date} | Monto: {amount} | Estado: {state}"
            )
        return "\n".join(lines)

    return json.dumps(rows, ensure_ascii=False)


def _execute_deterministic_plan(intent_name: str, plan: dict, question: str, metrics: dict, memory: dict | None = None):
    tool_name = plan.get("tool")
    arguments = plan.get("arguments")
    if not tool_name or not isinstance(arguments, dict):
        return None

    arguments = apply_intent_defaults(intent_name, dict(arguments), question)
    semantic_error = validate_plan_semantics(intent_name, tool_name, arguments)
    if semantic_error:
        logger.warning("Deterministic semantic error: %s", semantic_error)
        return None

    response_memory = dict(memory) if isinstance(memory, dict) else {}

    if tool_name == "summary_operativo_hoy":
        answer = _execute_operational_summary_today(arguments, metrics)
        if answer is None:
            return None, response_memory
        return answer, response_memory
    if tool_name == "summary_pickings_por_estado":
        answer = _execute_pickings_status_summary(arguments, metrics)
        if answer is None:
            return None, response_memory
        return answer, response_memory

    update_metrics_from_tool(metrics, tool_name, arguments)
    metrics["tool_calls"] += 1
    metrics["tools_used"].append(tool_name)
    tool_result = execute_tool(tool_name, arguments)
    update_quality_metrics_from_tool_result(metrics, tool_name, arguments, tool_result)
    logger.info("Deterministic result '%s': %s", tool_name, str(tool_result)[:300])
    entity_source = "explicit" if _query_has_explicit_entity_hint(question) else "inferred"

    entity = _extract_entity_from_tool_result(arguments.get("model"), tool_result, tool_name, arguments)
    if not entity and tool_name == "query_odoo_search":
        entity = _extract_entity_from_search_result(arguments.get("model"), tool_result, arguments)
        entity = _hydrate_entity_display_name(entity)
    if entity:
        if metrics.get("entity_consistent") is not False:
            metrics["entity_consistent"] = True
        response_memory = update_last_entity(response_memory, entity, question, source=entity_source)

    if isinstance(tool_result, dict) and "error" in tool_result:
        metrics["tool_success"] = False
        return None, response_memory

    if tool_name == "query_odoo_count":
        return f"Total: {tool_result}.", response_memory

    if tool_name == "query_odoo_group":
        rows = tool_result if isinstance(tool_result, list) else []
        if not rows:
            return "No hay datos para ese criterio.", response_memory
        groupby = arguments.get("groupby") or []
        preferred_metric_fields = _resolve_preferred_group_metrics(arguments)
        if intent_name == "promedio_ventas_por_cliente_periodo":
            total_value = 0.0
            for row in rows:
                value = row.get("amount_total")
                try:
                    total_value += float(value or 0.0)
                except Exception:
                    continue
            group_count = len(rows)
            avg_value = round(total_value / group_count, 2) if group_count else 0.0
            return f"Promedio por cliente: {avg_value} (clientes: {group_count}).", response_memory
        if intent_name == "clientes_facturas_vencidas_ranking":
            return _format_clientes_facturas_vencidas_ranking(rows), response_memory
        return _format_read_group_rows(rows, groupby, preferred_metric_fields=preferred_metric_fields), response_memory

    if tool_name == "query_odoo_search" and "read_back" in plan:
        ids = tool_result if isinstance(tool_result, list) else []
        if not ids:
            return "No hay registros.", response_memory
        read_args = dict(plan["read_back"])
        read_args.pop("tool", None)
        read_args["model"] = arguments.get("model")
        read_args["ids"] = ids
        update_metrics_from_tool(metrics, "query_odoo_read", read_args)
        metrics["tool_calls"] += 1
        metrics["tools_used"].append("query_odoo_read")
        read_result = execute_tool("query_odoo_read", read_args)
        update_quality_metrics_from_tool_result(metrics, "query_odoo_read", read_args, read_result)
        if isinstance(read_result, dict) and "error" in read_result:
            return None, response_memory
        entity = _extract_entity_from_tool_result(read_args.get("model"), read_result, "query_odoo_read", read_args)
        if entity:
            if metrics.get("entity_consistent") is not False:
                metrics["entity_consistent"] = True
            response_memory = update_last_entity(response_memory, entity, question, source=entity_source)
        formatted = _format_deterministic_read_answer(intent_name, read_args.get("model"), read_result)
        return formatted, response_memory

    return None, response_memory


def _find_clarification_rule(rule_name: str | None) -> dict | None:
    if not rule_name:
        return None
    for rule in CLARIFICATION_RULES:
        if rule.get("name") == rule_name:
            return rule
    return None


def _entity_model_human_label(model: str | None) -> str:
    mapping = {
        "sale.order": "venta",
        "purchase.order": "compra",
        "account.move": "factura",
        "sale.order.line": "línea de venta",
        "purchase.order.line": "línea de compra",
    }
    return mapping.get(model or "", "registro")


def _build_followup_pending_clarification(followup_clarification: dict | None, question: str) -> dict | None:
    if not isinstance(followup_clarification, dict):
        return None
    candidates = followup_clarification.get("entity_candidates")
    if not isinstance(candidates, list) or not candidates:
        return None

    options = []
    for index, candidate in enumerate(candidates, start=1):
        if not isinstance(candidate, dict):
            continue
        model = candidate.get("model")
        entity_id = candidate.get("id")
        if not isinstance(model, str) or not isinstance(entity_id, int):
            continue
        display_name = candidate.get("display_name") or f"ID {entity_id}"
        model_label = _entity_model_human_label(model)
        options.append(
            {
                "key": f"entity_{index}",
                "label": f"{model_label.title()} {display_name}",
                "value": f"{model_label} {display_name}",
                "model": model,
                "id": entity_id,
                "display_name": display_name,
                "source": candidate.get("source"),
            }
        )

    if not options:
        return None

    return {
        "name": "entity_followup_scope",
        "question": followup_clarification.get("question") or "¿A qué documento te refieres?",
        "original_question": question,
        "followup_intent": followup_clarification.get("intent"),
        "options": options,
    }


def _clarification_choice_to_ui(choice_key: str) -> dict:
    mapping = {
        "count": {"label": "Solo total", "value": "total"},
        "list": {"label": "Detalle", "value": "detalle"},
        "sale_orders": {"label": "Pedidos de venta", "value": "pedidos de venta"},
        "invoices": {"label": "Facturas emitidas", "value": "facturas emitidas"},
        "individual": {"label": "Individual", "value": "individual"},
        "total": {"label": "Acumulado", "value": "acumulado"},
    }
    return mapping.get(choice_key, {"label": choice_key.replace("_", " ").title(), "value": choice_key})


def _build_ui_clarification(memory: dict | None) -> dict | None:
    if not isinstance(memory, dict):
        return None
    pending = memory.get("pending_clarification")
    if not isinstance(pending, dict):
        return None

    rule = _find_clarification_rule(pending.get("name"))
    question = pending.get("question")
    options = []

    pending_options = pending.get("options")
    if isinstance(pending_options, list) and pending_options:
        for opt in pending_options:
            if not isinstance(opt, dict):
                continue
            key = opt.get("key") or ""
            label = opt.get("label") or opt.get("display_name") or key
            value = opt.get("value") or label
            if not key or not label:
                continue
            options.append(
                {
                    "key": key,
                    "label": label,
                    "value": value,
                    "model": opt.get("model"),
                    "id": opt.get("id"),
                    "display_name": opt.get("display_name"),
                    "source": opt.get("source"),
                }
            )

    if isinstance(rule, dict):
        question = question or rule.get("question")
        for choice_key in (rule.get("choices") or {}).keys():
            choice_ui = _clarification_choice_to_ui(choice_key)
            options.append({
                "key": choice_key,
                "label": choice_ui["label"],
                "value": choice_ui["value"],
            })

    return {
        "required": True,
        "question": question or "Necesito una precisión para responder mejor.",
        "options": options,
    }


def _detect_ui_mode(metrics: dict) -> str:
    if metrics.get("clarification_asked"):
        return "clarification"
    if metrics.get("followup_resolved"):
        return "memory"
    if metrics.get("intent_detected") and metrics.get("tokens_input", 0) == 0 and metrics.get("tool_calls", 0) > 0:
        return "deterministic"
    if metrics.get("tool_calls", 0) > 0:
        return "tool_call"
    return "llm"


def _build_ui_badges(metrics: dict, mode: str) -> list[str]:
    badges = []
    if mode == "clarification":
        badges.append("Aclaración requerida")
    elif mode == "memory":
        badges.append("Memoria")
    elif mode == "deterministic":
        badges.append("Determinístico")
    elif mode == "tool_call":
        badges.append("Tool call")

    if metrics.get("grounded"):
        badges.append("Con datos ERP")

    output = []
    seen = set()
    for badge in badges:
        if badge not in seen:
            output.append(badge)
            seen.add(badge)
    return output


def _build_ui_context(memory: dict | None) -> dict:
    if not isinstance(memory, dict):
        return {"active": "Sin contexto activo"}

    primary = memory.get("primary_entity")
    if not isinstance(primary, dict):
        return {"active": "Sin contexto activo"}

    model = primary.get("model")
    entity_id = primary.get("id")
    name = primary.get("display_name") or f"{model or 'registro'} #{entity_id or '?'}"
    pieces = [name]

    fields = primary.get("fields")
    if isinstance(fields, dict):
        partner = fields.get("partner_id")
        if isinstance(partner, (list, tuple)) and len(partner) >= 2:
            pieces.append(str(partner[1]))

    return {
        "active": " · ".join([p for p in pieces if p]),
        "model": model,
        "id": entity_id,
    }


def _build_ui_navigation(metrics: dict, memory: dict | None) -> dict:
    model = metrics.get("semantic_model") or metrics.get("model_used")
    domain = metrics.get("domain_used") if isinstance(metrics.get("domain_used"), list) else []
    orderby = metrics.get("orderby_used") if isinstance(metrics.get("orderby_used"), str) else None
    limit = metrics.get("limit_used") if isinstance(metrics.get("limit_used"), int) else None

    payload = {
        "model": model,
        "domain": domain,
        "orderby": orderby,
        "limit": limit,
    }

    if isinstance(metrics.get("ui_active_model"), str) and isinstance(metrics.get("ui_active_id"), int):
        payload["active_model"] = metrics.get("ui_active_model")
        payload["active_id"] = metrics.get("ui_active_id")
    elif isinstance(memory, dict):
        primary = memory.get("primary_entity")
        primary_model = primary.get("model") if isinstance(primary, dict) else None
        should_use_memory_entity = bool(metrics.get("memory_hit") or metrics.get("followup_resolved"))
        if not should_use_memory_entity and isinstance(primary_model, str) and isinstance(model, str):
            should_use_memory_entity = primary_model == model
        if isinstance(primary, dict) and should_use_memory_entity:
            payload["active_model"] = primary.get("model")
            payload["active_id"] = primary.get("id")
    return payload


def _build_ui_actions(metrics: dict) -> list[dict]:
    model = metrics.get("semantic_model") or metrics.get("model_used")
    domain = metrics.get("domain_used") if isinstance(metrics.get("domain_used"), list) else []
    active_model = metrics.get("ui_active_model")
    active_id = metrics.get("ui_active_id")
    orderby = metrics.get("orderby_used") if isinstance(metrics.get("orderby_used"), str) else None
    limit = metrics.get("limit_used") if isinstance(metrics.get("limit_used"), int) else None
    actions: list[dict] = []

    if model == "product.product":
        actions.extend([
            {
                "key": "open_products",
                "label": "Abrir productos",
                "type": "open_model_list",
                "model": "product.product",
                "domain": domain or [["qty_available", "<", 0]],
                "orderby": orderby,
                "limit": limit,
            },
            {"key": "stock_moves", "label": "Ver movimientos", "prompt": "muéstrame los últimos movimientos de stock"},
        ])
    elif model == "sale.order":
        actions.extend([
            {
                "key": "open_sales",
                "label": "Abrir ventas",
                "type": "open_model_list",
                "model": "sale.order",
                "domain": domain,
                "orderby": orderby,
                "limit": limit,
            },
            {"key": "open_invoices", "label": "Ver facturas", "prompt": "muéstrame las facturas relacionadas con esta venta"},
            {"key": "order_products", "label": "Ver productos", "prompt": "qué productos se vendieron en esta venta"},
        ])
    elif model == "account.move":
        actions.extend([
            {
                "key": "open_invoices_list",
                "label": "Abrir facturas",
                "type": "open_model_list",
                "model": "account.move",
                "domain": domain,
                "orderby": orderby,
                "limit": limit,
            },
            {"key": "due_invoices", "label": "Ver vencimientos", "prompt": "muéstrame las facturas vencidas"},
            {"key": "invoice_total", "label": "Solo total", "prompt": "dame solo el total"},
        ])

    if isinstance(active_id, int) and isinstance(active_model, str):
        actions.insert(0, {
            "key": "open_active_record",
            "label": "Abrir registro",
            "type": "open_record",
            "model": active_model,
            "id": active_id,
        })

    if metrics.get("grounded"):
        actions.append({"key": "export_csv", "label": "Exportar CSV"})

    output = []
    seen = set()
    for action in actions:
        key = action.get("key")
        if key and key not in seen:
            output.append(action)
            seen.add(key)
    return output[:4]


def _build_ui_suggestions(metrics: dict) -> list[dict]:
    model = metrics.get("semantic_model") or metrics.get("model_used")
    if model == "product.product":
        return [
            {"label": "Stock negativo", "prompt": "qué productos tienen stock negativo"},
            {"label": "Sin rotación", "prompt": "qué productos no tienen rotación este mes"},
            {"label": "Movimientos recientes", "prompt": "últimos movimientos de inventario"},
        ]
    if model == "sale.order":
        return [
            {"label": "Cantidad de ventas", "prompt": "cuántas ventas hay"},
            {"label": "Top clientes ventas", "prompt": "top clientes por ventas"},
            {"label": "Monto de ventas", "prompt": "monto total de ventas del mes"},
        ]
    if model == "purchase.order":
        return [
            {"label": "Cantidad de compras", "prompt": "cuántas compras hay"},
            {"label": "Top proveedores", "prompt": "top proveedores por compras"},
            {"label": "Política de compras", "prompt": "cómo funciona la política de aprobación de compras"},
        ]
    if model == "account.move":
        return [
            {"label": "Cantidad de facturas", "prompt": "cuántas facturas hay"},
            {"label": "Facturación clientes", "prompt": "top clientes por facturación"},
            {"label": "Facturas vencidas", "prompt": "cuántas facturas vencidas hay"},
        ]
    return [
        {"label": "Cantidad de ventas", "prompt": "cuántas ventas hay"},
        {"label": "Top clientes ventas", "prompt": "top clientes por ventas"},
        {"label": "Cantidad de compras", "prompt": "cuántas compras hay"},
        {"label": "Top proveedores", "prompt": "top proveedores por compras"},
        {"label": "Facturación clientes", "prompt": "top clientes por facturación"},
        {"label": "Política de compras", "prompt": "cómo funciona la política de aprobación de compras"},
    ]


def _build_ui_payload(metrics: dict, memory: dict | None, success: bool, error_type: str | None = None) -> dict:
    mode = _detect_ui_mode(metrics)
    clarification = _build_ui_clarification(memory)
    navigation = _build_ui_navigation(metrics, memory)
    metrics["ui_active_model"] = navigation.get("active_model")
    metrics["ui_active_id"] = navigation.get("active_id")
    return {
        "mode": mode,
        "status": "ok" if success else "error",
        "error_type": error_type,
        "latency_ms": metrics.get("latency_ms_total"),
        "badges": _build_ui_badges(metrics, mode),
        "context": _build_ui_context(memory),
        "navigation": navigation,
        "clarification": clarification,
        "actions": [] if clarification else _build_ui_actions(metrics),
        "suggestions": _build_ui_suggestions(metrics),
        "meta": {
            "intent": metrics.get("intent_detected"),
            "semantic_action": metrics.get("semantic_action"),
            "semantic_model": metrics.get("semantic_model"),
            "warnings": metrics.get("warnings") or [],
        },
    }


ERROR_CODE_MAP = {
    "rate_limit": "ERR_RATE_LIMIT",
    "api_error": "ERR_TOOL_TIMEOUT",
    "unknown_error": "ERR_INTERNAL",
    "invalid_ids": "ERR_INVALID_ID",
    "no_tool_for_data": "ERR_NO_TOOL",
    "repeated_tool_call": "ERR_REPEATED_TOOL_CALL",
    "followup_not_found": "ERR_NO_RESULTS",
    "related_followup_search_error": "ERR_TOOL_EXECUTION",
    "related_followup_read_error": "ERR_TOOL_EXECUTION",
    "max_iterations": "ERR_MAX_ITERATIONS",
}


def _map_error_code(error_type: str | None) -> str | None:
    if not error_type:
        return None
    if error_type in ERROR_CODE_MAP:
        return ERROR_CODE_MAP[error_type]
    if error_type.startswith("odoo_http_"):
        return "ERR_TOOL_HTTP"
    if "schema" in error_type or "invalido" in error_type or "invalid" in error_type:
        return "ERR_INVALID_FIELD"
    if "permission" in error_type:
        return "ERR_PERMISSION_DENIED"
    if "clarification" in error_type:
        return "ERR_AMBIGUOUS_CONTEXT"
    return "ERR_INTERNAL"


def _resolve_answer_mode(metrics: dict) -> str:
    if metrics.get("clarification_asked"):
        return "clarification_required"
    if metrics.get("intent_detected") and metrics.get("tokens_input", 0) == 0 and metrics.get("tool_calls", 0) > 0:
        return "deterministic"
    if metrics.get("tool_calls", 0) > 0:
        return "tool_guided"
    return "fallback_explanatory"


def _resolve_answer_type(answer: str, answer_mode: str, success: bool) -> str:
    if not success:
        return "error"
    if answer_mode == "clarification_required":
        return "clarification"
    text = (answer or "").strip().lower()
    if "\n1." in (answer or "") or "resultados:" in text or "|" in (answer or ""):
        return "table"
    if text.startswith("total:") or text.startswith("promedio"):
        return "summary"
    return "summary"


def _build_context_scope(context: dict | None) -> dict:
    if not isinstance(context, dict):
        return {}
    company = context.get("company") if isinstance(context.get("company"), dict) else {}
    client = context.get("client") if isinstance(context.get("client"), dict) else {}
    return {
        "company_id": company.get("id"),
        "active_model": client.get("active_model"),
        "active_id": client.get("active_id"),
        "lang": context.get("lang"),
        "tz": context.get("tz"),
    }


def _build_response_payload(
    answer: str,
    success: bool,
    error_type: str | None,
    metrics: dict,
    response_memory: dict,
    ui_payload: dict,
    context: dict | None,
) -> dict:
    answer_mode = _resolve_answer_mode(metrics)
    answer_type = _resolve_answer_type(answer, answer_mode, success)
    clarification = ui_payload.get("clarification") if isinstance(ui_payload, dict) else None
    clarification_options = clarification.get("options") if isinstance(clarification, dict) else []
    actions = ui_payload.get("actions") if isinstance(ui_payload, dict) else []

    return {
        "answer": answer,
        "answer_mode": answer_mode,
        "answer_type": answer_type,
        "needs_clarification": bool(answer_mode == "clarification_required"),
        "clarification_options": clarification_options or [],
        "actions": actions or [],
        "error_code": _map_error_code(error_type),
        "request_id": metrics.get("request_id"),
        "metadata": {
            "latency_ms": metrics.get("latency_ms_total"),
            "tools_used": metrics.get("tools_used") or [],
            "tool_calls": metrics.get("tool_calls"),
            "tool_trace": metrics.get("tool_trace") or [],
            "tokens_input": metrics.get("tokens_input"),
            "tokens_output": metrics.get("tokens_output"),
            "route_selected": metrics.get("route_selected"),
            "context_scope": _build_context_scope(context),
        },
        "ui": ui_payload,
        "memory": response_memory,
    }


def ask_agent(question: str, context: dict | None = None, history: list | None = None, max_iterations: int = 3) -> dict:
    start_ts = time.perf_counter()
    request_id = None
    if isinstance(context, dict):
        request_id = context.get("request_id")
        if not request_id:
            client = context.get("client")
            if isinstance(client, dict):
                request_id = client.get("request_id")
    if not request_id:
        request_id = f"req_{uuid.uuid4().hex[:12]}"

    metrics = {
        "request_id": request_id,
        "query": question,
        "tools_used": [],
        "tool_trace": [],
        "tool_calls": 0,
        "iterations": 0,
        "tokens_input": 0,
        "tokens_output": 0,
        "cost": 0.0,
        "success": False,
        "success_response_emitted": False,
        "tool_success": None,
        "partial_failure": False,
        "error_type": None,
        "grounded": False,
        "invalid_id_blocked": False,
        "memory_hit": False,
        "followup_resolved": False,
        "followup_bypassed_llm": False,
        "clarification_asked": False,
        "clarification_resolved": False,
        "entity_consistent": None,
        "ranking_preserved": None,
        "response_faithful": None,
        "route_selected": None,
        "entity_source_used": None,
        "entity_candidates": [],
        "entity_conflict_detected": False,
        "followup_confidence": None,
        "clarification_reason": None,
        "ui_context_overridden": False,
    }
    response_memory = dict(get_session_memory(context))
    ui_entity = _context_ui_entity(context)
    if ui_entity:
        response_memory = set_last_ui_entity(response_memory, ui_entity, source_query="ui_context")
        metrics["ui_active_model"] = ui_entity.get("model")
        metrics["ui_active_id"] = ui_entity.get("id")

    def _finalize(answer: str, success: bool, error_type: str | None = None):
        metrics["success"] = success
        metrics["error_type"] = error_type
        metrics["success_response_emitted"] = bool(success)
        if metrics.get("tool_success") is None:
            metrics["tool_success"] = True if metrics.get("tool_calls", 0) > 0 else None
        if isinstance(error_type, str) and metrics.get("tool_calls", 0) > 0:
            if error_type.startswith("odoo_http_") or "tool" in error_type:
                metrics["tool_success"] = False
        metrics["partial_failure"] = bool(metrics.get("success_response_emitted") and metrics.get("tool_success") is False)
        metrics["latency_ms_total"] = int((time.perf_counter() - start_ts) * 1000)
        metrics["cost"] = round(
            (metrics["tokens_input"] / 1000.0) * LLM_COST_INPUT_PER_1K
            + (metrics["tokens_output"] / 1000.0) * LLM_COST_OUTPUT_PER_1K,
            6,
        )

        metrics.setdefault("intent_detected", None)
        metrics.setdefault("model_used", None)
        metrics.setdefault("domain_used", None)
        metrics.setdefault("fields_used", None)
        metrics.setdefault("orderby_used", None)
        metrics.setdefault("limit_used", None)
        metrics.setdefault("entity_consistent", None)
        metrics.setdefault("ranking_preserved", None)
        metrics.setdefault("entity_source_used", None)
        metrics.setdefault("entity_candidates", [])
        metrics.setdefault("entity_conflict_detected", False)
        metrics.setdefault("followup_confidence", None)
        metrics.setdefault("clarification_reason", None)
        metrics.setdefault("ui_context_overridden", False)
        if metrics.get("response_faithful") is None:
            if success and metrics.get("grounded"):
                metrics["response_faithful"] = True
            elif _is_data_question(question) and not metrics.get("grounded"):
                metrics["response_faithful"] = False

        evaluate_metrics(metrics)

        ui_payload = _build_ui_payload(metrics, response_memory, success=success, error_type=error_type)
        payload = _build_response_payload(
            answer=answer,
            success=success,
            error_type=error_type,
            metrics=metrics,
            response_memory=response_memory,
            ui_payload=ui_payload,
            context=context,
        )
        log_agent_event(
            "finalize",
            request_id=metrics.get("request_id"),
            success=success,
            route_selected=metrics.get("route_selected"),
            error_type=error_type,
            tool_calls=metrics.get("tool_calls"),
            tokens_input=metrics.get("tokens_input"),
            tokens_output=metrics.get("tokens_output"),
            latency_ms=metrics.get("latency_ms_total"),
        )
        logger.info("METRICS %s", json.dumps(metrics, ensure_ascii=False, default=str))
        logger.info(
            "RESPONSE %s",
            json.dumps(
                {
                    "request_id": payload.get("request_id"),
                    "answer_mode": payload.get("answer_mode"),
                    "answer_type": payload.get("answer_type"),
                    "needs_clarification": payload.get("needs_clarification"),
                    "error_code": payload.get("error_code"),
                },
                ensure_ascii=False,
                default=str,
            ),
        )
        return payload

    clarification_was_resolved = False
    clarification_result = resolve_pending_clarification(question, response_memory)
    if clarification_result:
        if clarification_result.get("resolved"):
            question = clarification_result["rewritten_question"]
            selected_entity = clarification_result.get("selected_entity")
            if isinstance(selected_entity, dict):
                response_memory = update_last_entity(
                    response_memory,
                    selected_entity,
                    question,
                    source="explicit",
                )
                response_memory = _clear_resolved_entity_conflicts(response_memory, selected_entity)
            response_memory = set_pending_clarification(response_memory, None)
            metrics["clarification_resolved"] = True
            clarification_was_resolved = True
        else:
            metrics["clarification_asked"] = True
            metrics["route_selected"] = AgentRoute.CLARIFICATION
            return _finalize(clarification_result["question"], success=True)

    if not clarification_was_resolved:
        clarification_needed = detect_clarification_needed(question, response_memory)
        if clarification_needed:
            response_memory = set_pending_clarification(response_memory, clarification_needed)
            metrics["clarification_asked"] = True
            metrics["route_selected"] = AgentRoute.CLARIFICATION
            return _finalize(clarification_needed["question"], success=True)

    query_has_explicit_entity_hint = _query_has_explicit_entity_hint(question)

    deterministic = _try_deterministic_path(question)
    catalog_intent = deterministic["intent"] if deterministic else None
    intent_plan = deterministic["plan"] if deterministic else None
    semantic_frame = deterministic.get("semantic_frame") if deterministic else None
    metrics["intent_detected"] = catalog_intent or detect_intent(question)
    if isinstance(semantic_frame, dict):
        metrics["semantic_action"] = semantic_frame.get("action")
        metrics["semantic_model"] = semantic_frame.get("model")

    last_entity = get_last_entity({"memory": response_memory})
    if not clarification_was_resolved:
        followup_clarification = needs_followup_clarification(question, last_entity, response_memory)
        if followup_clarification:
            followup_pending = _build_followup_pending_clarification(followup_clarification, question)
            if followup_pending:
                response_memory = set_pending_clarification(response_memory, followup_pending)
            metrics["entity_candidates"] = followup_clarification.get("entity_candidates") or []
            metrics["entity_conflict_detected"] = bool(followup_clarification.get("entity_conflict_detected"))
            metrics["followup_confidence"] = followup_clarification.get("followup_confidence")
            metrics["clarification_reason"] = followup_clarification.get("reason")
            metrics["clarification_asked"] = True
            metrics["route_selected"] = AgentRoute.CLARIFICATION
            return _finalize(followup_clarification.get("question") or "¿A qué registro te refieres exactamente?", success=True)

    followup = resolve_followup(question, last_entity, response_memory)
    if followup and followup.get("type") == "entity_followup":
        metrics["route_selected"] = AgentRoute.MEMORY_ENTITY
        metrics["memory_hit"] = True
        metrics["followup_resolved"] = True
        metrics["followup_bypassed_llm"] = True
        if metrics.get("entity_consistent") is not False:
            metrics["entity_consistent"] = True
        metrics["entity_source_used"] = "last_entity"
        metrics["entity_candidates"] = []
        metrics["entity_conflict_detected"] = False
        metrics["followup_confidence"] = 0.8
        read_args = {
            "model": followup["model"],
            "ids": [followup["id"]],
            "fields": _followup_read_fields(followup["model"]),
        }
        update_metrics_from_tool(metrics, "query_odoo_read", read_args)
        metrics["tool_calls"] += 1
        metrics["tools_used"].append("query_odoo_read")
        tool_result = execute_tool("query_odoo_read", read_args)
        update_quality_metrics_from_tool_result(metrics, "query_odoo_read", read_args, tool_result)
        metrics["grounded"] = True
        if isinstance(tool_result, list) and tool_result:
            entity = _extract_entity_from_tool_result(followup["model"], tool_result, "query_odoo_read", read_args)
            if entity:
                if metrics.get("entity_consistent") is not False:
                    metrics["entity_consistent"] = True
                entity_source = "explicit" if query_has_explicit_entity_hint else "inferred"
                response_memory = update_last_entity(response_memory, entity, question, source=entity_source)
            return _finalize(
                _format_followup_answer(followup["model"], tool_result[0], followup.get("display_name")),
                success=True,
            )
        return _finalize("No encontré el registro solicitado.", success=False, error_type="followup_not_found")

    if followup and followup.get("type") == "related_followup":
        metrics["route_selected"] = AgentRoute.MEMORY_RELATED
        metrics["memory_hit"] = True
        metrics["followup_resolved"] = True
        metrics["followup_bypassed_llm"] = True
        metrics["grounded"] = True
        metrics["entity_source_used"] = followup.get("entity_source_used")
        metrics["entity_candidates"] = followup.get("entity_candidates") or []
        metrics["entity_conflict_detected"] = bool(followup.get("entity_conflict_detected"))
        metrics["followup_confidence"] = followup.get("followup_confidence")
        if isinstance(ui_entity, dict) and metrics.get("entity_source_used") == "last_explicit_entity":
            selected_model = followup.get("source_model")
            selected_id = followup.get("source_id")
            if selected_model and isinstance(selected_id, int):
                metrics["ui_context_overridden"] = (
                    ui_entity.get("model") != selected_model or ui_entity.get("id") != selected_id
                )
        if metrics.get("entity_consistent") is not False:
            metrics["entity_consistent"] = True
        answer, error_type = _execute_related_followup(followup, question, metrics)
        if answer is not None:
            return _finalize(answer, success=True)
        return _finalize(
            "No pude resolver la relación solicitada para el registro anterior.",
            success=False,
            error_type=error_type or "related_followup_error",
        )

    if deterministic and intent_plan:
        metrics["route_selected"] = AgentRoute.DETERMINISTIC
        answer, response_memory = _execute_deterministic_plan(catalog_intent, intent_plan, question, metrics, response_memory)
        if answer is not None:
            metrics["grounded"] = True
            return _finalize(answer, success=True)
        logger.warning("Deterministic path failed for intent '%s'; fallback to LLM without forced plan.", catalog_intent)
        intent_plan = None
        catalog_intent = None

    family = detect_intent_family(question)

    messages = [{"role": "system", "content": load_prompt("system_base.txt") }]
    messages.append({"role": "system", "content": build_date_context_prompt()})
    family_prompt = family_prompt_path(family)
    if family_prompt:
        messages.append({"role": "system", "content": load_prompt(family_prompt)})

    if context:
        ctx_json = compress_context(context)
        if ctx_json:
            messages.append({"role": "system", "content": f"Contexto funcional: {ctx_json}"})
    if semantic_frame:
        frame_json = compress_context(semantic_frame)
        if frame_json:
            messages.append({"role": "system", "content": f"Marco semántico normalizado: {frame_json}"})

    combined_history = []
    skip_history = deterministic is not None
    if not skip_history:
        if context and isinstance(context, dict):
            server_hist = context.get("history_server")
            if isinstance(server_hist, list):
                combined_history.extend(server_hist)
        if history and isinstance(history, list):
            combined_history.extend(history)

    if combined_history:
        ctx_limit = None
        if context and isinstance(context, dict):
            try:
                ctx_limit = int(context.get("history_limit"))
            except Exception:
                ctx_limit = None
        limit = ctx_limit if ctx_limit is not None else DEFAULT_MAX_HISTORY
        if limit < 0:
            limit = 0
        if context and isinstance(context, dict) and context.get("use_server_history") is False:
            combined_history = [h for h in combined_history if h.get("source") != "server"]
        selected = combined_history[-limit:] if limit else []
        for item in selected:
            role = item.get("role")
            text = item.get("text") or ""
            if role == "user":
                messages.append({"role": "user", "content": text})
            elif role in ("bot", "assistant"):
                messages.append({"role": "assistant", "content": text})

    messages.append({"role": "user", "content": question})

    def _get_response_memory():
        return response_memory

    def _set_response_memory(next_memory: dict):
        nonlocal response_memory
        response_memory = next_memory

    callbacks = ToolLoopCallbacks(
        is_data_question=_is_data_question,
        is_amount_followup=_is_amount_followup,
        is_count_question=_is_count_question,
        extract_partner_ids_from_domain=_extract_partner_ids_from_domain,
        extract_ids_from_domain=_extract_ids_from_domain,
        normalize_read_group_args=_normalize_read_group_args,
        normalize_read_fields_with_schema=_normalize_read_fields_with_schema,
        enforce_invoice_semantics=_enforce_invoice_semantics,
        detect_avg_group_intent=_detect_avg_group_intent,
        compute_avg_from_group_rows=_compute_avg_from_group_rows,
        extract_entity_from_tool_result=_extract_entity_from_tool_result,
        extract_entity_from_search_result=_extract_entity_from_search_result,
        hydrate_entity_display_name=_hydrate_entity_display_name,
        get_response_memory=_get_response_memory,
        set_response_memory=_set_response_memory,
    )

    return run_tool_guided_loop(
        question=question,
        messages=messages,
        max_iterations=max_iterations,
        metrics=metrics,
        intent_plan=intent_plan,
        catalog_intent=catalog_intent,
        query_has_explicit_entity_hint=query_has_explicit_entity_hint,
        context=context,
        finalize=lambda answer, success, error_type=None: _finalize(answer, success=success, error_type=error_type),
        callbacks=callbacks,
    )
