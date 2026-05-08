from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from app.agents.types import AgentContext, Entity, ToolArguments, ToolExecutionResult, ToolStep
from app.observability import emit_event
from app.tools.knowledge_tools import run_search_knowledge
from app.tools.odoo_tools import query_odoo_count, query_odoo_group, query_odoo_read, query_odoo_search


TOOL_REGISTRY = {
    "query_odoo_search": query_odoo_search,
    "query_odoo_read": query_odoo_read,
    "query_odoo_count": query_odoo_count,
    "query_odoo_group": query_odoo_group,
    "search_knowledge": run_search_knowledge,
}
ODOO_TOOL_PREFIX = "query_odoo_"
logger = logging.getLogger("odoo_ai_service")

MODEL_ENTITY_LABELS = {
    "sale.order": "la venta",
    "sale.order.line": "la línea de venta",
    "purchase.order": "la compra",
    "purchase.order.line": "la línea de compra",
    "account.move": "la factura",
    "stock.picking": "el picking",
    "res.partner": "el contacto",
    "product.product": "el producto",
}


def _entity_not_found_message(entity: Entity | None, arguments: ToolArguments | None = None) -> str:
    model = None
    if isinstance(entity, dict):
        model = entity.get("model")
    if not model and isinstance(arguments, dict):
        model = arguments.get("model")
    label = MODEL_ENTITY_LABELS.get(model, "la entidad solicitada")
    code = entity.get("code") if isinstance(entity, dict) and entity.get("code") else None
    return f"No encontré {label} {code}." if code else f"No encontré {label}."


def _resolve_dynamic_args(arguments: ToolArguments, previous_result: Any) -> ToolArguments:
    resolved = dict(arguments or {})
    if resolved.get("ids") == "$previous_result":
        if isinstance(previous_result, list) and previous_result and all(isinstance(item, int) for item in previous_result):
            resolved["ids"] = previous_result
        elif isinstance(previous_result, list) and previous_result and isinstance(previous_result[0], dict):
            ids = [row.get("id") for row in previous_result if isinstance(row, dict) and isinstance(row.get("id"), int)]
            resolved["ids"] = ids
        else:
            resolved["ids"] = []
    return resolved


def _attach_runtime_context(tool_name: str | None, arguments: ToolArguments, context: AgentContext | dict | None) -> ToolArguments:
    resolved = dict(arguments or {})
    if tool_name and tool_name.startswith(ODOO_TOOL_PREFIX) and isinstance(context, dict):
        resolved.setdefault("context", context)
    return resolved


def _trace_id_from_context(context: AgentContext | dict | None) -> str | None:
    if not isinstance(context, dict):
        return None
    trace_id = context.get("request_id")
    return str(trace_id) if trace_id else None


def _public_arguments(arguments: ToolArguments) -> ToolArguments:
    public_args = dict(arguments or {})
    public_args.pop("context", None)
    return public_args


def _failure_result(
    *,
    error_type: str,
    message: str,
    tools_used: list[str],
    results: list[dict],
    partial_failure: bool,
    trace_id: str | None = None,
) -> ToolExecutionResult:
    payload: ToolExecutionResult = {
        "success": False,
        "error_type": error_type,
        "message": message,
        "tools_used": tools_used,
        "results": results,
        "partial_failure": partial_failure,
    }
    if trace_id:
        payload["trace_id"] = trace_id
    return payload


def execute_plan(plan: list[ToolStep], entity: Entity | None = None, context: AgentContext | dict | None = None) -> ToolExecutionResult:
    tools_used: list[str] = []
    results: list[dict] = []
    previous_result: Any = None
    partial_failure = False
    trace_id = _trace_id_from_context(context)

    for step in plan:
        tool_name = step.get("tool")
        arguments = _resolve_dynamic_args(step.get("args") or {}, previous_result)
        arguments = _attach_runtime_context(tool_name, arguments, context)
        if tool_name == "query_odoo_read" and not arguments.get("ids"):
            return _failure_result(
                error_type="entity_not_found",
                message=_entity_not_found_message(entity, arguments),
                tools_used=tools_used,
                results=results,
                partial_failure=partial_failure,
                trace_id=trace_id,
            )

        tool_fn = TOOL_REGISTRY.get(tool_name)
        if tool_fn is None:
            return _failure_result(
                error_type="tool_not_found",
                message=f"Tool no registrada: {tool_name}",
                tools_used=tools_used,
                results=results,
                partial_failure=partial_failure,
                trace_id=trace_id,
            )

        tool_started_at = perf_counter()
        try:
            result = tool_fn(**arguments)
        except Exception:
            latency_ms = round((perf_counter() - tool_started_at) * 1000, 2)
            partial_failure = bool(tools_used)
            logger.exception(
                "tool_execution_failed trace_id=%s tool=%s model=%s",
                trace_id,
                tool_name,
                arguments.get("model"),
            )
            emit_event(
                logger,
                "TOOL_ERROR",
                trace_id=trace_id,
                tool=tool_name,
                model=arguments.get("model"),
                latency_ms=latency_ms,
                error_type="tool_exception",
            )
            return _failure_result(
                error_type="tool_exception",
                message=f"No pude ejecutar {tool_name}. Trace ID: {trace_id}" if trace_id else f"No pude ejecutar {tool_name}.",
                tools_used=tools_used,
                results=results,
                partial_failure=partial_failure,
                trace_id=trace_id,
            )
        tools_used.append(tool_name)
        results.append({"tool": tool_name, "args": _public_arguments(arguments), "result": result})
        previous_result = result
        latency_ms = round((perf_counter() - tool_started_at) * 1000, 2)
        emit_event(
            logger,
            "TOOL_EXECUTED",
            trace_id=trace_id,
            tool=tool_name,
            model=arguments.get("model"),
            latency_ms=latency_ms,
            success=not (isinstance(result, dict) and result.get("error")),
            error_type=result.get("error") if isinstance(result, dict) else None,
        )

        if isinstance(result, dict) and result.get("error"):
            partial_failure = True
            return _failure_result(
                error_type=str(result.get("error")),
                message=f"Error ejecutando {tool_name}: {result.get('error')}",
                tools_used=tools_used,
                results=results,
                partial_failure=partial_failure,
                trace_id=trace_id,
            )

        if tool_name == "query_odoo_search" and isinstance(result, list) and not result:
            return _failure_result(
                error_type="entity_not_found",
                message=_entity_not_found_message(entity, arguments),
                tools_used=tools_used,
                results=results,
                partial_failure=partial_failure,
                trace_id=trace_id,
            )

    payload: ToolExecutionResult = {
        "success": True,
        "tools_used": tools_used,
        "results": results,
        "partial_failure": partial_failure,
    }
    if trace_id:
        payload["trace_id"] = trace_id
    return payload
