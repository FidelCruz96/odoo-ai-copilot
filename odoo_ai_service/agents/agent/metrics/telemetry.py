from __future__ import annotations

from typing import Any


def _parse_orderby(orderby: str | None) -> tuple[str | None, str | None]:
    if not isinstance(orderby, str):
        return None, None
    parts = orderby.strip().split()
    if len(parts) < 2:
        return None, None
    field = parts[0]
    direction = parts[1].lower()
    if direction not in ("asc", "desc"):
        return None, None
    return field, direction


def _to_sortable_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, (list, tuple)) and value:
        return _to_sortable_number(value[0])
    if isinstance(value, str):
        try:
            return float(value)
        except Exception:
            return None
    return None


def _compute_ranking_preserved(orderby: str | None, result) -> bool | None:
    field, direction = _parse_orderby(orderby)
    if not field or direction not in ("asc", "desc"):
        return None
    if not isinstance(result, list) or len(result) < 2:
        return None

    values = []
    for row in result:
        if not isinstance(row, dict):
            continue
        values.append(_to_sortable_number(row.get(field)))

    values = [v for v in values if isinstance(v, (int, float))]
    if len(values) < 2:
        return None

    if direction == "desc":
        return all(values[i] >= values[i + 1] for i in range(len(values) - 1))
    return all(values[i] <= values[i + 1] for i in range(len(values) - 1))


def evaluate_metrics(metrics: dict[str, Any]) -> None:
    warnings: list[str] = []

    iterations = metrics.get("iterations", 0) or 0
    latency_ms_total = metrics.get("latency_ms_total", 0) or 0
    tokens_input = metrics.get("tokens_input", 0) or 0
    tool_calls = metrics.get("tool_calls", 0) or 0

    if iterations > 2:
        warnings.append("high_iterations")
    if latency_ms_total > 4500:
        warnings.append("high_latency")
    if tokens_input > 3200:
        warnings.append("high_tokens")
    if tool_calls > 2:
        warnings.append("high_tool_calls")

    if metrics.get("entity_consistent") is False:
        warnings.append("entity_inconsistent")
    if metrics.get("ranking_preserved") is False:
        warnings.append("ranking_not_preserved")
    if metrics.get("response_faithful") is False:
        warnings.append("response_not_faithful")

    metrics["warnings"] = warnings
    metrics["pass_optimo"] = len(warnings) == 0


def update_metrics_from_tool(metrics: dict, tool_name: str, arguments: dict) -> None:
    if not isinstance(arguments, dict):
        return

    model = arguments.get("model")
    if model:
        metrics["model_used"] = model
    elif tool_name == "get_schema":
        models = arguments.get("models")
        if isinstance(models, list) and models:
            metrics["model_used"] = models[0] if len(models) == 1 else models

    if "domain" in arguments:
        metrics["domain_used"] = arguments.get("domain")
    if "fields" in arguments:
        metrics["fields_used"] = arguments.get("fields")
    if "orderby" in arguments:
        metrics["orderby_used"] = arguments.get("orderby")
    if "limit" in arguments:
        metrics["limit_used"] = arguments.get("limit")


def update_quality_metrics_from_tool_result(metrics: dict, tool_name: str, arguments: dict, result) -> None:
    if not isinstance(metrics, dict):
        return
    if not isinstance(arguments, dict):
        return

    if tool_name == "query_odoo_group":
        ranking = _compute_ranking_preserved(arguments.get("orderby"), result)
        if ranking is not None:
            if metrics.get("ranking_preserved") is False:
                return
            metrics["ranking_preserved"] = bool(ranking)
