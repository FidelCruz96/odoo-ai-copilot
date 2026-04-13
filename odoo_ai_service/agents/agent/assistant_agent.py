import json
import logging
import os
import time
import re
from datetime import date, timedelta

from openai import RateLimitError, APIError, APIConnectionError

from llm.llm_client import call_llm
from tools.tool_definitions import tools

from .execution.tool_executor import execute_tool
from .execution.result_compressor import compress_tool_result
from .execution.session_state import SessionState
from .clarification_resolver import detect_clarification_needed, resolve_pending_clarification
from .intents.intent_matcher import detect_intent, detect_intent_family, detect_catalog_intent
from .intents.planner import build_entities, build_intent_plan
from .intents.semantic_frame import build_semantic_frame, resolve_intent_variant, apply_frame_to_plan
from .intents.defaults import apply_intent_defaults, apply_query_guardrails
from .memory_store import get_last_entity, get_session_memory, set_pending_clarification, update_last_entity
from .reference_resolver import resolve_followup
from .validators.domain_validator import normalize_domain_operators, validate_domain
from .validators.schema_validator import get_model_schema, validate_against_schema
from .validators.semantic_validator import validate_plan_semantics
from .metrics.telemetry import evaluate_metrics, update_metrics_from_tool, update_quality_metrics_from_tool_result

logger = logging.getLogger(__name__)

DEFAULT_MAX_HISTORY = int(os.getenv("AI_CHAT_HISTORY_LIMIT", "8"))
LLM_COST_INPUT_PER_1K = float(os.getenv("LLM_COST_INPUT_PER_1K", "0"))
LLM_COST_OUTPUT_PER_1K = float(os.getenv("LLM_COST_OUTPUT_PER_1K", "0"))

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


def _load_prompt(name: str) -> str:
    path = os.path.join(PROMPTS_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip() + "\n"


def _build_date_context_prompt() -> str:
    today = date.today()
    year = today.year
    month = today.month

    month_start = today.replace(day=1)
    month_end = (
        today.replace(month=month % 12 + 1, day=1) - timedelta(days=1)
        if month < 12 else today.replace(day=31)
    )

    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    last_year_start = today.replace(year=year - 1, month=1, day=1)
    last_year_end = today.replace(year=year - 1, month=12, day=31)

    last_month_year = year if month > 1 else year - 1
    last_month = month - 1 if month > 1 else 12
    last_month_start = today.replace(year=last_month_year, month=last_month, day=1)
    last_month_end = (
        today.replace(year=last_month_year, month=last_month % 12 + 1, day=1) - timedelta(days=1)
        if last_month < 12 else today.replace(year=last_month_year, month=last_month, day=31)
    )

    year_start = today.replace(month=1, day=1)
    year_end = today.replace(month=12, day=31)

    return (
        f"Hoy es {today}.\n"
        "Rangos útiles:\n"
        f"- hoy: {today}\n"
        f"- inicio_mes: {month_start}\n"
        f"- fin_mes: {month_end}\n"
        f"- inicio_año: {year_start}\n"
        f"- fin_año: {year_end}\n"
        f"- inicio_semana: {week_start}\n"
        f"- fin_semana: {week_end}\n"
        f"- año_pasado_inicio: {last_year_start}\n"
        f"- año_pasado_fin: {last_year_end}\n"
        f"- mes_pasado_inicio: {last_month_start}\n"
        f"- mes_pasado_fin: {last_month_end}\n"
    )


def _family_prompt_path(family: str) -> str | None:
    mapping = {
        "ventas": "family_ventas.txt",
        "compras": "family_compras.txt",
        "facturacion": "family_facturacion.txt",
        "clientes": "family_clientes.txt",
        "productos": "family_productos.txt",
        "inventario": "family_inventario.txt",
    }
    return mapping.get(family)


def _compress_context(context: dict | None) -> str | None:
    if not context:
        return None
    try:
        return json.dumps(context, ensure_ascii=False)
    except Exception:
        return str(context)


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

    return "No encontré información relacionada."


def _execute_related_followup(plan: dict, question: str, metrics: dict):
    search_plan = plan.get("search") or {}
    search_args = {
        "model": search_plan.get("model"),
        "domain": search_plan.get("domain") or [],
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

    if model in ("sale.order", "purchase.order"):
        header = "Órdenes encontradas:"
        lines = [header]
        for index, row in enumerate(rows[:20], start=1):
            name = row.get("name") or f"ID {row.get('id')}"
            partner = row.get("partner_id")
            partner_name = partner[1] if isinstance(partner, (list, tuple)) and len(partner) >= 2 else "-"
            date_value = row.get("date_order") or "-"
            amount = row.get("amount_total", "-")
            state = row.get("state", "-")
            lines.append(
                f"{index}. {name} | Contacto: {partner_name} | Fecha: {date_value} | Monto: {amount} | Estado: {state}"
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

    update_metrics_from_tool(metrics, tool_name, arguments)
    metrics["tool_calls"] += 1
    metrics["tools_used"].append(tool_name)
    tool_result = execute_tool(tool_name, arguments)
    update_quality_metrics_from_tool_result(metrics, tool_name, arguments, tool_result)
    logger.info("Deterministic result '%s': %s", tool_name, str(tool_result)[:300])
    response_memory = dict(memory) if isinstance(memory, dict) else {}

    entity = _extract_entity_from_tool_result(arguments.get("model"), tool_result, tool_name, arguments)
    if entity:
        if metrics.get("entity_consistent") is not False:
            metrics["entity_consistent"] = True
        response_memory = update_last_entity(response_memory, entity, question)

    if isinstance(tool_result, dict) and "error" in tool_result:
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
            response_memory = update_last_entity(response_memory, entity, question)
        formatted = _format_deterministic_read_answer(intent_name, read_args.get("model"), read_result)
        return formatted, response_memory

    return None, response_memory


def ask_agent(question: str, context: dict | None = None, history: list | None = None, max_iterations: int = 8) -> dict:
    start_ts = time.perf_counter()
    metrics = {
        "query": question,
        "tools_used": [],
        "tool_calls": 0,
        "iterations": 0,
        "tokens_input": 0,
        "tokens_output": 0,
        "cost": 0.0,
        "success": False,
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
    }
    response_memory = dict(get_session_memory(context))

    def _finalize(answer: str, success: bool, error_type: str | None = None):
        metrics["success"] = success
        metrics["error_type"] = error_type
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
        if metrics.get("response_faithful") is None:
            if success and metrics.get("grounded"):
                metrics["response_faithful"] = True
            elif _is_data_question(question) and not metrics.get("grounded"):
                metrics["response_faithful"] = False

        evaluate_metrics(metrics)

        logger.info("METRICS %s", json.dumps(metrics, ensure_ascii=False, default=str))
        return {"answer": answer, "memory": response_memory}

    clarification_was_resolved = False
    clarification_result = resolve_pending_clarification(question, response_memory)
    if clarification_result:
        if clarification_result.get("resolved"):
            question = clarification_result["rewritten_question"]
            response_memory = set_pending_clarification(response_memory, None)
            metrics["clarification_resolved"] = True
            clarification_was_resolved = True
        else:
            metrics["clarification_asked"] = True
            return _finalize(clarification_result["question"], success=True)

    if not clarification_was_resolved:
        clarification_needed = detect_clarification_needed(question, response_memory)
        if clarification_needed:
            response_memory = set_pending_clarification(response_memory, clarification_needed)
            metrics["clarification_asked"] = True
            return _finalize(clarification_needed["question"], success=True)

    deterministic = _try_deterministic_path(question)
    catalog_intent = deterministic["intent"] if deterministic else None
    intent_plan = deterministic["plan"] if deterministic else None
    semantic_frame = deterministic.get("semantic_frame") if deterministic else None
    metrics["intent_detected"] = catalog_intent or detect_intent(question)
    if isinstance(semantic_frame, dict):
        metrics["semantic_action"] = semantic_frame.get("action")
        metrics["semantic_model"] = semantic_frame.get("model")

    followup = resolve_followup(question, get_last_entity(context))
    if followup and followup.get("type") == "entity_followup":
        metrics["memory_hit"] = True
        metrics["followup_resolved"] = True
        metrics["followup_bypassed_llm"] = True
        if metrics.get("entity_consistent") is not False:
            metrics["entity_consistent"] = True
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
                response_memory = update_last_entity(response_memory, entity, question)
            return _finalize(
                _format_followup_answer(followup["model"], tool_result[0], followup.get("display_name")),
                success=True,
            )
        return _finalize("No encontré el registro solicitado.", success=False, error_type="followup_not_found")

    if followup and followup.get("type") == "related_followup":
        metrics["memory_hit"] = True
        metrics["followup_resolved"] = True
        metrics["followup_bypassed_llm"] = True
        metrics["grounded"] = True
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
        answer, response_memory = _execute_deterministic_plan(catalog_intent, intent_plan, question, metrics, response_memory)
        if answer is not None:
            metrics["grounded"] = True
            return _finalize(answer, success=True)

    family = detect_intent_family(question)

    messages = [{"role": "system", "content": _load_prompt("system_base.txt") }]
    messages.append({"role": "system", "content": _build_date_context_prompt()})
    family_prompt = _family_prompt_path(family)
    if family_prompt:
        messages.append({"role": "system", "content": _load_prompt(family_prompt)})

    if context:
        ctx_json = _compress_context(context)
        if ctx_json:
            messages.append({"role": "system", "content": f"Contexto funcional: {ctx_json}"})
    if semantic_frame:
        frame_json = _compress_context(semantic_frame)
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

    schema_cache = {}
    state = SessionState()

    for iteration in range(max_iterations):
        metrics["iterations"] = iteration + 1
        logger.info(f"Iteración {iteration + 1}/{max_iterations}")

        try:
            response = call_llm(messages, tools)
        except RateLimitError:
            return _finalize(
                "El servicio de IA está temporalmente saturado por límite de tokens. Intenta nuevamente en unos segundos.",
                success=False,
                error_type="rate_limit",
            )
        except (APIError, APIConnectionError):
            return _finalize(
                "No pude conectar con el servicio de IA. Intenta nuevamente.",
                success=False,
                error_type="api_error",
            )
        except Exception:
            return _finalize(
                "Ocurrió un error inesperado en el servicio de IA.",
                success=False,
                error_type="unknown_error",
            )

        message = response.choices[0].message
        logger.info(f"LLM RESPONSE: {message}")
        if hasattr(response, "usage") and response.usage:
            metrics["tokens_input"] += getattr(response.usage, "prompt_tokens", 0) or 0
            metrics["tokens_output"] += getattr(response.usage, "completion_tokens", 0) or 0

        if not message.tool_calls:
            if _is_data_question(question) and not state.used_tool_in_session:
                return _finalize(
                    "Para responder necesito consultar Odoo con una herramienta. ¿Puedes reformular o especificar exactamente qué datos necesitas?",
                    success=False,
                    error_type="no_tool_for_data",
                )
            return _finalize(message.content or "No se obtuvo respuesta.", success=True)

        messages.append(message)

        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            logger.info(f"TOOL CALL: {tool_name}")
            metrics["tool_calls"] += 1
            metrics["tools_used"].append(tool_name)

            if tool_name not in {"get_schema", "query_odoo_search", "query_odoo_read", "query_odoo_group", "query_odoo_count"}:
                tool_result = f"Error: herramienta '{tool_name}' no encontrada."
                logger.warning(tool_result)
            else:
                try:
                    arguments = json.loads(tool_call.function.arguments)

                    if intent_plan:
                        if "read_back" in intent_plan and tool_name == "query_odoo_read":
                            read_args = dict(intent_plan["read_back"])
                            read_args["ids"] = arguments.get("ids") or []
                            arguments = read_args
                        else:
                            tool_name = intent_plan["tool"]
                            arguments = dict(intent_plan["arguments"])

                    if catalog_intent:
                        arguments = apply_intent_defaults(catalog_intent, arguments, question)
                        if not (intent_plan and "read_back" in intent_plan and tool_name == "query_odoo_read"):
                            semantic_error = validate_plan_semantics(catalog_intent, tool_name, arguments)
                            if semantic_error:
                                return _finalize(
                                    "La consulta no cumple las reglas semánticas de la intención. ¿Puedes reformular la pregunta?",
                                    success=False,
                                    error_type=semantic_error,
                                )
                    else:
                        arguments = apply_query_guardrails(tool_name, arguments, question)

                    tool_sig = f"{tool_name}:{json.dumps(arguments, sort_keys=True, ensure_ascii=False)}"
                    if tool_sig == state.last_tool_sig:
                        state.repeated_tool_calls += 1
                    else:
                        state.repeated_tool_calls = 0
                    state.last_tool_sig = tool_sig

                    if _is_amount_followup(question) and state.last_partner_ids:
                        if tool_name in ("query_odoo_search", "query_odoo_group"):
                            tool_name = "query_odoo_group"
                            arguments = {
                                "model": state.last_partner_model or "sale.order",
                                "domain": [["partner_id", "in", state.last_partner_ids]],
                                "fields": ["amount_total"],
                                "groupby": ["partner_id"],
                                "limit": len(state.last_partner_ids),
                            }

                    if tool_name == "query_odoo_search" and state.repeated_tool_calls >= 1 and _is_count_question(question):
                        tool_name = "query_odoo_count"

                    if state.repeated_tool_calls >= 2:
                        return _finalize(
                            "Parece que estoy repitiendo la misma consulta. ¿Podrías reformular la pregunta con más detalle?",
                            success=False,
                            error_type="repeated_tool_call",
                        )

                    if state.last_partner_ids and tool_name in ("query_odoo_search", "query_odoo_group", "query_odoo_read"):
                        domain_ids = _extract_partner_ids_from_domain(arguments.get("domain"))
                        if domain_ids and not set(domain_ids).issubset(set(state.last_partner_ids)):
                            metrics["invalid_id_blocked"] = True
                            metrics["entity_consistent"] = False
                            return _finalize(
                                "Necesito los clientes exactos para calcular el monto. ¿Puedes confirmar los clientes o repetir la consulta anterior?",
                                success=False,
                                error_type="invalid_ids",
                            )

                    if tool_name in ("query_odoo_search", "query_odoo_group", "query_odoo_read"):
                        model = arguments.get("model")
                        domain_pairs = _extract_ids_from_domain(arguments.get("domain"))
                        for field, ids in domain_pairs:
                            key = (model, field)
                            allowed = state.last_ids_by_model_field.get(key)
                            if allowed is not None and ids and not set(ids).issubset(allowed):
                                metrics["invalid_id_blocked"] = True
                                metrics["entity_consistent"] = False
                                return _finalize(
                                    "Necesito los IDs exactos devueltos por una consulta previa. ¿Puedes confirmar los registros o repetir la consulta anterior?",
                                    success=False,
                                    error_type="invalid_ids",
                                )

                    if tool_name == "get_schema":
                        models = arguments.get("models")
                        if not models or not isinstance(models, list):
                            tool_result = "Error de validación: get_schema requiere 'models' como lista de modelos."
                            logger.error(tool_result)
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": compress_tool_result(tool_name, tool_result),
                            })
                            continue

                    if "domain" in arguments:
                        arguments["domain"] = normalize_domain_operators(arguments["domain"])
                        arguments["domain"] = validate_domain(arguments["domain"])

                    if tool_name in ("query_odoo_search", "query_odoo_read", "query_odoo_group", "query_odoo_count"):
                        model_name = arguments.get("model")
                        model_info = get_model_schema(schema_cache, model_name)
                        if tool_name == "query_odoo_group":
                            arguments = _normalize_read_group_args(arguments, question)
                        validation_error = validate_against_schema(
                            {model_name: model_info} if model_info else {},
                            model_name,
                            fields=arguments.get("fields"),
                            groupby=arguments.get("groupby"),
                            domain=arguments.get("domain"),
                            orderby=arguments.get("orderby"),
                        )
                        if validation_error:
                            tool_result = f"Error de schema: {validation_error}"
                            logger.error(tool_result)
                            raise ValueError(validation_error)

                    update_metrics_from_tool(metrics, tool_name, arguments)
                    tool_result = execute_tool(tool_name, arguments)
                    update_quality_metrics_from_tool_result(metrics, tool_name, arguments, tool_result)
                    logger.info(f"Resultado '{tool_name}': {str(tool_result)[:300]}")

                    state.used_tool_in_session = True
                    metrics["grounded"] = True

                    if tool_name == "query_odoo_group":
                        avg_group_intent = _detect_avg_group_intent(question)
                        if avg_group_intent:
                            try:
                                entity_field = avg_group_intent["entity"]

                                if arguments.get("model") in ("sale.order", "purchase.order"):
                                    value_field = "amount_total"
                                elif arguments.get("model") == "sale.order.line":
                                    value_field = "product_uom_qty"
                                elif arguments.get("model") == "purchase.order.line":
                                    value_field = "product_qty"
                                else:
                                    value_field = "amount_total"

                                stats = _compute_avg_from_group_rows(
                                    tool_result,
                                    entity_field=entity_field,
                                    value_field=value_field,
                                )

                                if stats and stats["group_count"] > 0:
                                    tool_result = {
                                        "metric": "average_by_group",
                                        "entity": avg_group_intent["label"],
                                        "entity_field": entity_field,
                                        "group_count": stats["group_count"],
                                        "total_value": stats["total_value"],
                                        "average_value": stats["average_value"],
                                        "source_model": arguments.get("model"),
                                        "source_value_field": value_field,
                                    }
                                    logger.info("Resultado '%s' postprocess average_by_group: %s", tool_name, str(tool_result)[:300])
                            except Exception:
                                logger.exception("avg group postprocess failed")

                    if tool_name == "query_odoo_group":
                        try:
                            if arguments.get("model") and "partner_id" in (arguments.get("groupby") or []):
                                ids = []
                                for row in (tool_result or []):
                                    partner_val = row.get("partner_id")
                                    if isinstance(partner_val, (list, tuple)) and partner_val:
                                        ids.append(partner_val[0])
                                if ids:
                                    state.last_partner_ids = ids
                                    state.last_partner_model = arguments.get("model")
                        except Exception:
                            pass

                    if tool_name == "query_odoo_group":
                        try:
                            model = arguments.get("model")
                            groupby = arguments.get("groupby") or []
                            for field in groupby:
                                ids = []
                                for row in (tool_result or []):
                                    val = row.get(field)
                                    if isinstance(val, (list, tuple)) and val:
                                        ids.append(val[0])
                                    elif isinstance(val, int):
                                        ids.append(val)
                                if ids:
                                    state.last_ids_by_model_field[(model, field)] = set(ids)
                        except Exception:
                            pass

                    if tool_name == "query_odoo_group":
                        try:
                            if arguments.get("model") == "sale.order" and "user_id" in (arguments.get("groupby") or []):
                                rows = tool_result if isinstance(tool_result, list) else []
                                if rows and rows[0].get("user_id") is False:
                                    domain = arguments.get("domain") or []
                                    domain = [d for d in domain if not (isinstance(d, (list, tuple)) and len(d) == 3 and d[0] == "user_id")]
                                    domain.append(["user_id", "!=", False])
                                    retry_args = dict(arguments)
                                    retry_args["domain"] = domain
                                    tool_result = execute_tool(tool_name, retry_args)
                                    update_quality_metrics_from_tool_result(metrics, tool_name, retry_args, tool_result)
                                    logger.info("Resultado '%s' retry user_id!=False: %s", tool_name, str(tool_result)[:300])
                        except Exception:
                            pass

                    entity = _extract_entity_from_tool_result(arguments.get("model"), tool_result, tool_name, arguments)
                    if entity:
                        if metrics.get("entity_consistent") is not False:
                            metrics["entity_consistent"] = True
                        response_memory = update_last_entity(response_memory, entity, question)

                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error en tool_call: {e}")
                    tool_result = "Error: argumentos inválidos en tool_call (JSON malformado)."
                except ValueError as e:
                    tool_result = f"Error de validación: {str(e)}"
                except Exception as e:
                    logger.exception("Tool call failed")
                    tool_result = f"Error ejecutando la herramienta {tool_name}: {str(e)}"

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": compress_tool_result(tool_name, tool_result),
            })

    return _finalize(
        "No pude completar la consulta tras varios intentos. Intenta reformular la pregunta.",
        success=False,
        error_type="max_iterations",
    )
