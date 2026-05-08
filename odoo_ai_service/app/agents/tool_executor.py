from __future__ import annotations

from typing import Any

from app.agents.types import AgentContext, Entity, ToolArguments, ToolExecutionResult, ToolStep
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


def execute_plan(plan: list[ToolStep], entity: Entity | None = None, context: AgentContext | dict | None = None) -> ToolExecutionResult:
    tools_used: list[str] = []
    results: list[dict] = []
    previous_result: Any = None
    partial_failure = False

    for step in plan:
        tool_name = step.get("tool")
        arguments = _resolve_dynamic_args(step.get("args") or {}, previous_result)
        arguments = _attach_runtime_context(tool_name, arguments, context)
        if tool_name == "query_odoo_read" and not arguments.get("ids"):
            return {
                "success": False,
                "error_type": "entity_not_found",
                "message": _entity_not_found_message(entity, arguments),
                "tools_used": tools_used,
                "results": results,
                "partial_failure": partial_failure,
            }

        tool_fn = TOOL_REGISTRY.get(tool_name)
        if tool_fn is None:
            return {
                "success": False,
                "error_type": "tool_not_found",
                "message": f"Tool no registrada: {tool_name}",
                "tools_used": tools_used,
                "results": results,
                "partial_failure": partial_failure,
            }

        result = tool_fn(**arguments)
        tools_used.append(tool_name)
        results.append({"tool": tool_name, "args": arguments, "result": result})
        previous_result = result

        if isinstance(result, dict) and result.get("error"):
            partial_failure = True
            return {
                "success": False,
                "error_type": result.get("error"),
                "message": f"Error ejecutando {tool_name}: {result.get('error')}",
                "tools_used": tools_used,
                "results": results,
                "partial_failure": partial_failure,
            }

        if tool_name == "query_odoo_search" and isinstance(result, list) and not result:
            return {
                "success": False,
                "error_type": "entity_not_found",
                "message": _entity_not_found_message(entity, arguments),
                "tools_used": tools_used,
                "results": results,
                "partial_failure": partial_failure,
            }

    return {
        "success": True,
        "tools_used": tools_used,
        "results": results,
        "partial_failure": partial_failure,
    }
