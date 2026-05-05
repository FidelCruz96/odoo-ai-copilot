from __future__ import annotations

from typing import Any, Callable


def _error(tool_name: str, field: str, message: str) -> dict:
    return {
        "error": "invalid_tool_arguments",
        "tool": tool_name,
        "details": [{"field": field, "message": message}],
    }


def _reject_extra(tool_name: str, payload: dict, allowed: set[str]) -> dict | None:
    extra = sorted(set(payload) - allowed)
    if extra:
        return _error(tool_name, ",".join(extra), "extra fields are not allowed")
    return None


def _require_string(tool_name: str, payload: dict, field: str) -> dict | None:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        return _error(tool_name, field, "must be a non-empty string")
    return None


def _require_string_list(tool_name: str, payload: dict, field: str) -> dict | None:
    value = payload.get(field)
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        return _error(tool_name, field, "must be a list of non-empty strings")
    return None


def _require_int_list(tool_name: str, payload: dict, field: str) -> dict | None:
    value = payload.get(field)
    if not isinstance(value, list) or not value:
        return _error(tool_name, field, "must be a non-empty list of integers")
    try:
        payload[field] = [int(item) for item in value]
    except Exception:
        return _error(tool_name, field, "must be a non-empty list of integers")
    return None


def _validate_optional_list(tool_name: str, payload: dict, field: str) -> dict | None:
    value = payload.get(field)
    if value is None:
        payload[field] = []
        return None
    if not isinstance(value, list):
        return _error(tool_name, field, "must be a list")
    return None


def _validate_optional_int(tool_name: str, payload: dict, field: str) -> dict | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, int):
        return _error(tool_name, field, "must be an integer")
    return None


def _validate_optional_string(tool_name: str, payload: dict, field: str) -> dict | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        return _error(tool_name, field, "must be a string")
    return None


def _validate_get_schema(arguments: dict) -> tuple[dict | None, dict | None]:
    tool_name = "get_schema"
    payload = dict(arguments)
    allowed = {"models", "force"}
    for validator in (
        lambda: _reject_extra(tool_name, payload, allowed),
        lambda: _require_string_list(tool_name, payload, "models"),
    ):
        err = validator()
        if err:
            return None, err
    payload["force"] = bool(payload.get("force", False))
    return payload, None


def _validate_search(arguments: dict) -> tuple[dict | None, dict | None]:
    tool_name = "query_odoo_search"
    payload = {"domain": [], "orderby": None, "limit": 20, **dict(arguments)}
    allowed = {"model", "domain", "orderby", "limit"}
    for validator in (
        lambda: _reject_extra(tool_name, payload, allowed),
        lambda: _require_string(tool_name, payload, "model"),
        lambda: _validate_optional_list(tool_name, payload, "domain"),
        lambda: _validate_optional_string(tool_name, payload, "orderby"),
        lambda: _validate_optional_int(tool_name, payload, "limit"),
    ):
        err = validator()
        if err:
            return None, err
    return payload, None


def _validate_count(arguments: dict) -> tuple[dict | None, dict | None]:
    tool_name = "query_odoo_count"
    payload = {"domain": [], "limit": None, **dict(arguments)}
    allowed = {"model", "domain", "limit"}
    for validator in (
        lambda: _reject_extra(tool_name, payload, allowed),
        lambda: _require_string(tool_name, payload, "model"),
        lambda: _validate_optional_list(tool_name, payload, "domain"),
        lambda: _validate_optional_int(tool_name, payload, "limit"),
    ):
        err = validator()
        if err:
            return None, err
    return payload, None


def _validate_read(arguments: dict) -> tuple[dict | None, dict | None]:
    tool_name = "query_odoo_read"
    payload = dict(arguments)
    allowed = {"model", "ids", "fields"}
    for validator in (
        lambda: _reject_extra(tool_name, payload, allowed),
        lambda: _require_string(tool_name, payload, "model"),
        lambda: _require_int_list(tool_name, payload, "ids"),
        lambda: _require_string_list(tool_name, payload, "fields"),
    ):
        err = validator()
        if err:
            return None, err
    return payload, None


def _validate_group(arguments: dict) -> tuple[dict | None, dict | None]:
    tool_name = "query_odoo_group"
    payload = {"domain": [], "orderby": None, "limit": None, **dict(arguments)}
    allowed = {"model", "domain", "fields", "groupby", "orderby", "limit"}
    for validator in (
        lambda: _reject_extra(tool_name, payload, allowed),
        lambda: _require_string(tool_name, payload, "model"),
        lambda: _validate_optional_list(tool_name, payload, "domain"),
        lambda: _require_string_list(tool_name, payload, "fields"),
        lambda: _require_string_list(tool_name, payload, "groupby"),
        lambda: _validate_optional_string(tool_name, payload, "orderby"),
        lambda: _validate_optional_int(tool_name, payload, "limit"),
    ):
        err = validator()
        if err:
            return None, err
    return payload, None


TOOL_ARG_SCHEMAS: dict[str, Callable[[dict], tuple[dict | None, dict | None]]] = {
    "get_schema": _validate_get_schema,
    "query_odoo_search": _validate_search,
    "query_odoo_count": _validate_count,
    "query_odoo_read": _validate_read,
    "query_odoo_group": _validate_group,
}


def validate_tool_arguments(tool_name: str, arguments: dict | None) -> tuple[dict | None, dict | None]:
    validator = TOOL_ARG_SCHEMAS.get(tool_name)
    if validator is None:
        return None, {"error": f"tool_not_found:{tool_name}"}
    if arguments is not None and not isinstance(arguments, dict):
        return None, _error(tool_name, "arguments", "must be an object")
    return validator(arguments or {})
