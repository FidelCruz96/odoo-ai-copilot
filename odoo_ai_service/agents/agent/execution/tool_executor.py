from __future__ import annotations

from agents.agent.tool_schemas import validate_tool_arguments
from tools.odoo_get_tool import query_odoo, get_schema

TOOL_MAP = {
    "get_schema": lambda **kwargs: get_schema(**kwargs),
    "query_odoo_search": lambda **kwargs: query_odoo(operation="search", **{**kwargs, "limit": kwargs.get("limit", 20)}),
    "query_odoo_count": lambda **kwargs: query_odoo(operation="search_count", **kwargs),
    "query_odoo_read": lambda **kwargs: query_odoo(operation="read", **kwargs),
    "query_odoo_group": lambda **kwargs: query_odoo(operation="read_group", **kwargs),
}


def execute_tool(tool_name: str, arguments: dict):
    if tool_name not in TOOL_MAP:
        return {"error": f"tool_not_found:{tool_name}"}
    validated_arguments, validation_error = validate_tool_arguments(tool_name, arguments)
    if validation_error:
        return validation_error
    return TOOL_MAP[tool_name](**validated_arguments)
