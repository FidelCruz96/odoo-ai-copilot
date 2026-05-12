from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Callable

from openai import APIConnectionError, APIError, RateLimitError

from llm.llm_client import call_llm
from tools.tool_definitions import tools

from .execution.result_compressor import compress_tool_result
from .execution.session_state import SessionState
from .execution.tool_executor import execute_tool
from .intents.defaults import apply_intent_defaults, apply_query_guardrails
from .memory_store import update_last_entity
from .metrics.telemetry import update_metrics_from_tool, update_quality_metrics_from_tool_result
from .routes import AgentRoute
from .tracing import log_agent_event
from .validators.domain_validator import (
    coerce_domain_id_values,
    normalize_domain_operators,
    normalize_domain_values,
    validate_domain,
)
from .validators.schema_validator import get_model_schema, normalize_orderby, validate_against_schema
from .validators.semantic_validator import validate_plan_semantics

logger = logging.getLogger(__name__)

ALLOWED_TOOLS = {"get_schema", "query_odoo_search", "query_odoo_read", "query_odoo_group", "query_odoo_count"}


@dataclass
class ToolLoopCallbacks:
    is_data_question: Callable[[str], bool]
    is_amount_followup: Callable[[str], bool]
    is_count_question: Callable[[str], bool]
    extract_partner_ids_from_domain: Callable[[list | None], list]
    extract_ids_from_domain: Callable[[list | None], list]
    normalize_read_group_args: Callable[[dict, str], dict]
    normalize_read_fields_with_schema: Callable[[dict, dict | None], dict]
    enforce_invoice_semantics: Callable[[dict, str, dict | None, str, dict | None], dict]
    detect_avg_group_intent: Callable[[str], dict | None]
    compute_avg_from_group_rows: Callable[[list, str, str], dict | None]
    extract_entity_from_tool_result: Callable[[str | None, object, str, dict], dict | None]
    extract_entity_from_search_result: Callable[[str | None, object, dict], dict | None]
    hydrate_entity_display_name: Callable[[dict | None], dict | None]
    get_response_memory: Callable[[], dict]
    set_response_memory: Callable[[dict], None]


def _append_tool_result(messages: list, tool_call, tool_name: str, tool_result):
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": compress_tool_result(tool_name, tool_result),
    })


def run_tool_guided_loop(
    *,
    question: str,
    messages: list,
    max_iterations: int,
    metrics: dict,
    intent_plan: dict | None,
    catalog_intent: str | None,
    query_has_explicit_entity_hint: bool,
    context: dict | None = None,
    finalize: Callable[[str, bool, str | None], dict],
    callbacks: ToolLoopCallbacks,
) -> dict:
    schema_cache = {}
    state = SessionState()

    for iteration in range(max_iterations):
        metrics["route_selected"] = AgentRoute.TOOL_GUIDED
        metrics["iterations"] = iteration + 1
        logger.info("Iteración %s/%s", iteration + 1, max_iterations)

        try:
            response = call_llm(messages, tools)
        except RateLimitError:
            return finalize(
                "El servicio de IA está temporalmente saturado por límite de tokens. Intenta nuevamente en unos segundos.",
                False,
                "rate_limit",
            )
        except (APIError, APIConnectionError):
            return finalize("No pude conectar con el servicio de IA. Intenta nuevamente.", False, "api_error")
        except Exception:
            return finalize("Ocurrió un error inesperado en el servicio de IA.", False, "unknown_error")

        message = response.choices[0].message
        logger.info("LLM RESPONSE: %s", message)
        if hasattr(response, "usage") and response.usage:
            metrics["tokens_input"] += getattr(response.usage, "prompt_tokens", 0) or 0
            metrics["tokens_output"] += getattr(response.usage, "completion_tokens", 0) or 0

        if not message.tool_calls:
            if callbacks.is_data_question(question) and not state.used_tool_in_session:
                metrics["route_selected"] = AgentRoute.FALLBACK
                return finalize(
                    "Para responder necesito consultar Odoo con una herramienta. ¿Puedes reformular o especificar exactamente qué datos necesitas?",
                    False,
                    "no_tool_for_data",
                )
            metrics["route_selected"] = AgentRoute.FALLBACK
            return finalize(message.content or "No se obtuvo respuesta.", True, None)

        messages.append(message)

        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            logger.info("TOOL CALL: %s", tool_name)
            metrics["tool_calls"] += 1
            metrics["tools_used"].append(tool_name)

            if tool_name not in ALLOWED_TOOLS:
                tool_result = f"Error: herramienta '{tool_name}' no encontrada."
                logger.warning(tool_result)
                _append_tool_result(messages, tool_call, tool_name, tool_result)
                continue

            try:
                arguments = json.loads(tool_call.function.arguments)

                if intent_plan:
                    if tool_name == "get_schema":
                        pass
                    elif "read_back" in intent_plan and tool_name == "query_odoo_read":
                        read_args = dict(intent_plan["read_back"])
                        read_args["ids"] = arguments.get("ids") or []
                        arguments = read_args
                    else:
                        tool_name = intent_plan["tool"]
                        arguments = dict(intent_plan["arguments"])

                if catalog_intent:
                    if tool_name != "get_schema":
                        arguments = apply_intent_defaults(catalog_intent, arguments, question)
                        if not (intent_plan and "read_back" in intent_plan and tool_name == "query_odoo_read"):
                            semantic_error = validate_plan_semantics(catalog_intent, tool_name, arguments)
                            if semantic_error:
                                return finalize(
                                    "La consulta no cumple las reglas semánticas de la intención. ¿Puedes reformular la pregunta?",
                                    False,
                                    semantic_error,
                                )
                else:
                    arguments = apply_query_guardrails(tool_name, arguments, question)

                tool_sig = f"{tool_name}:{json.dumps(arguments, sort_keys=True, ensure_ascii=False)}"
                if tool_sig == state.last_tool_sig:
                    state.repeated_tool_calls += 1
                else:
                    state.repeated_tool_calls = 0
                state.last_tool_sig = tool_sig

                if callbacks.is_amount_followup(question) and state.last_partner_ids:
                    if tool_name in ("query_odoo_search", "query_odoo_group"):
                        tool_name = "query_odoo_group"
                        arguments = {
                            "model": state.last_partner_model or "sale.order",
                            "domain": [["partner_id", "in", state.last_partner_ids]],
                            "fields": ["amount_total"],
                            "groupby": ["partner_id"],
                            "limit": len(state.last_partner_ids),
                        }

                if tool_name == "query_odoo_search" and state.repeated_tool_calls >= 1 and callbacks.is_count_question(question):
                    tool_name = "query_odoo_count"

                if state.repeated_tool_calls >= 2:
                    return finalize(
                        "Parece que estoy repitiendo la misma consulta. ¿Podrías reformular la pregunta con más detalle?",
                        False,
                        "repeated_tool_call",
                    )

                if state.last_partner_ids and tool_name in ("query_odoo_search", "query_odoo_group", "query_odoo_read"):
                    domain_ids = callbacks.extract_partner_ids_from_domain(arguments.get("domain"))
                    if domain_ids and not set(domain_ids).issubset(set(state.last_partner_ids)):
                        metrics["invalid_id_blocked"] = True
                        metrics["entity_consistent"] = False
                        return finalize(
                            "Necesito los clientes exactos para calcular el monto. ¿Puedes confirmar los clientes o repetir la consulta anterior?",
                            False,
                            "invalid_ids",
                        )

                if tool_name in ("query_odoo_search", "query_odoo_group", "query_odoo_read"):
                    model = arguments.get("model")
                    domain_pairs = callbacks.extract_ids_from_domain(arguments.get("domain"))
                    for field, ids in domain_pairs:
                        key = (model, field)
                        allowed = state.last_ids_by_model_field.get(key)
                        if allowed is not None and ids and not set(ids).issubset(allowed):
                            metrics["invalid_id_blocked"] = True
                            metrics["entity_consistent"] = False
                            return finalize(
                                "Necesito los IDs exactos devueltos por una consulta previa. ¿Puedes confirmar los registros o repetir la consulta anterior?",
                                False,
                                "invalid_ids",
                            )

                if tool_name == "get_schema":
                    models = arguments.get("models")
                    if not models or not isinstance(models, list):
                        tool_result = "Error de validación: get_schema requiere 'models' como lista de modelos."
                        logger.error(tool_result)
                        _append_tool_result(messages, tool_call, tool_name, tool_result)
                        continue

                if "domain" in arguments:
                    arguments["domain"] = normalize_domain_operators(arguments["domain"])
                    arguments["domain"] = normalize_domain_values(arguments["domain"])
                    arguments["domain"] = coerce_domain_id_values(arguments["domain"])
                    arguments["domain"] = validate_domain(arguments["domain"])

                if tool_name == "query_odoo_read" and isinstance(arguments.get("ids"), list):
                    arguments["ids"] = [
                        int(v) if isinstance(v, str) and v.isdigit() else v
                        for v in arguments["ids"]
                    ]

                if isinstance(arguments.get("orderby"), str):
                    arguments["orderby"] = normalize_orderby(arguments.get("orderby"))

                if tool_name in ("query_odoo_search", "query_odoo_read", "query_odoo_group", "query_odoo_count"):
                    model_name = arguments.get("model")
                    model_info = get_model_schema(schema_cache, model_name)
                    if tool_name == "query_odoo_group":
                        arguments = callbacks.normalize_read_group_args(arguments, question)
                    if tool_name == "query_odoo_read":
                        arguments = callbacks.normalize_read_fields_with_schema(arguments, model_info)
                    arguments = callbacks.enforce_invoice_semantics(
                        arguments,
                        question,
                        callbacks.get_response_memory(),
                        tool_name,
                        model_info,
                    )
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
                    if context and "context" not in arguments:
                        arguments["context"] = context

                update_metrics_from_tool(metrics, tool_name, arguments)
                tool_start_ts = time.perf_counter()
                log_agent_event(
                    "tool_execute_start",
                    request_id=metrics.get("request_id"),
                    tool_name=tool_name,
                    arguments=arguments,
                )
                tool_result = execute_tool(tool_name, arguments)
                log_agent_event(
                    "tool_execute_end",
                    request_id=metrics.get("request_id"),
                    tool_name=tool_name,
                    latency_ms=int((time.perf_counter() - tool_start_ts) * 1000),
                    result_type=type(tool_result).__name__,
                    result_size=len(tool_result) if isinstance(tool_result, (list, dict, str)) else None,
                )
                update_quality_metrics_from_tool_result(metrics, tool_name, arguments, tool_result)
                if isinstance(tool_result, dict) and "error" in tool_result:
                    metrics["tool_success"] = False
                logger.info("Resultado '%s': %s", tool_name, str(tool_result)[:300])

                state.used_tool_in_session = True
                metrics["grounded"] = True

                if tool_name == "query_odoo_group":
                    avg_group_intent = callbacks.detect_avg_group_intent(question)
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

                            stats = callbacks.compute_avg_from_group_rows(
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

                entity = callbacks.extract_entity_from_tool_result(arguments.get("model"), tool_result, tool_name, arguments)
                if not entity and tool_name == "query_odoo_search":
                    entity = callbacks.extract_entity_from_search_result(arguments.get("model"), tool_result, arguments)
                    entity = callbacks.hydrate_entity_display_name(entity)
                if entity:
                    if metrics.get("entity_consistent") is not False:
                        metrics["entity_consistent"] = True
                    entity_source = "explicit" if query_has_explicit_entity_hint else "inferred"
                    callbacks.set_response_memory(
                        update_last_entity(callbacks.get_response_memory(), entity, question, source=entity_source)
                    )

            except json.JSONDecodeError as e:
                logger.error("JSON decode error en tool_call: %s", e)
                metrics["tool_success"] = False
                tool_result = "Error: argumentos inválidos en tool_call (JSON malformado)."
            except ValueError as e:
                metrics["tool_success"] = False
                tool_result = f"Error de validación: {str(e)}"
            except Exception as e:
                logger.exception("Tool call failed")
                metrics["tool_success"] = False
                tool_result = f"Error ejecutando la herramienta {tool_name}: {str(e)}"

            _append_tool_result(messages, tool_call, tool_name, tool_result)

    return finalize(
        "No pude completar la consulta tras varios intentos. Intenta reformular la pregunta.",
        False,
        "max_iterations",
    )
