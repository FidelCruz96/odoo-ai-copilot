from __future__ import annotations

from datetime import date, timedelta
import re

from .intent_catalog import INTENT_CATALOG
from .defaults import detect_period_range


def _default_range():
    today = date.today()
    start = today.replace(month=1, day=1)
    end = today.replace(month=12, day=31)
    return start, end


def render_domain(domain_template: list[list], values: dict) -> list[list]:
    rendered = []
    for clause in domain_template:
        new_clause = []
        for item in clause:
            if isinstance(item, str):
                try:
                    new_clause.append(item.format(**values))
                except KeyError:
                    new_clause.append(item)
            else:
                new_clause.append(item)
        rendered.append(new_clause)
    return rendered


def build_entities(question: str, top_n: int | None = None) -> dict:
    entities = {}
    period = detect_period_range(question)
    if period:
        date_start, date_end = period
    else:
        date_start, date_end = _default_range()

    entities["date_start"] = str(date_start)
    entities["date_end"] = str(date_end)
    entities["date_end_next"] = str(date_end + timedelta(days=1))
    entities["today"] = str(date.today())
    entities["today_start"] = f"{date.today()} 00:00:00"
    entities["tomorrow_start"] = f"{date.today() + timedelta(days=1)} 00:00:00"
    entities["month_start"] = str(date.today().replace(day=1))
    entities["month_end"] = str((date.today().replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1))
    if top_n is None:
        m = re.search(r"\\btop\\s+(\\d+)\\b", (question or "").lower())
        if m:
            try:
                top_n = int(m.group(1))
            except Exception:
                top_n = None
    if top_n is not None:
        entities["top_n"] = top_n
    return entities


def build_intent_plan(intent_name: str, entities: dict) -> dict | None:
    spec = INTENT_CATALOG.get(intent_name)
    if not spec:
        return None

    domain = render_domain(spec.domain_template, entities)

    if spec.operation == "search_read":
        return {
            "tool": "query_odoo_search",
            "arguments": {
                "model": spec.model,
                "domain": domain,
                "orderby": spec.orderby,
                "limit": entities.get("top_n", spec.limit_default),
            },
            "read_back": {
                "tool": "query_odoo_read",
                "fields": spec.default_fields,
            }
        }

    if spec.operation == "group":
        measure_field = "__count" if spec.measure_field == "__count" else f"{spec.measure_field}:sum"
        fields = [*spec.groupby]
        if measure_field != "__count":
            fields.append(measure_field)

        return {
            "tool": "query_odoo_group",
            "arguments": {
                "model": spec.model,
                "domain": domain,
                "fields": fields,
                "groupby": spec.groupby,
                "orderby": spec.orderby,
                "limit": entities.get("top_n", spec.limit_default),
            }
        }

    if spec.operation == "aggregate":
        return {
            "tool": "query_odoo_group",
            "arguments": {
                "model": spec.model,
                "domain": domain,
                "fields": [f"{spec.measure_field}:sum"],
                "groupby": [],
                "limit": 1,
            }
        }

    if spec.operation == "avg_group":
        fields = [*spec.groupby, f"{spec.measure_field}:sum"]
        return {
            "tool": "query_odoo_group",
            "arguments": {
                "model": spec.model,
                "domain": domain,
                "fields": fields,
                "groupby": spec.groupby,
                "limit": min(100, int(entities.get("top_n", spec.limit_default) or 100)),
            }
        }

    if spec.operation == "count":
        return {
            "tool": "query_odoo_count",
            "arguments": {
                "model": spec.model,
                "domain": domain,
            }
        }

    if spec.operation == "summary_operativo":
        return {
            "tool": "summary_operativo_hoy",
            "arguments": {
                "today": entities.get("today"),
                "today_start": entities.get("today_start"),
                "tomorrow_start": entities.get("tomorrow_start"),
            },
        }

    if spec.operation == "summary_pickings_estado":
        return {
            "tool": "summary_pickings_por_estado",
            "arguments": {},
        }

    return None
