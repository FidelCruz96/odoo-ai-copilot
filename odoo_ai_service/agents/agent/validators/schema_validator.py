from __future__ import annotations

import re

from tools.odoo_get_tool import get_schema

NUMERIC_TYPES = {"integer", "float", "monetary"}
ORDERBY_COUNT_VALUES = {"__count desc", "__count asc"}


def field_names_from_domain(domain):
    names = []
    if not isinstance(domain, list):
        return names
    for clause in domain:
        if isinstance(clause, (list, tuple)) and len(clause) == 3:
            names.append(clause[0])
    return names


def base_field(field: str) -> str:
    if not isinstance(field, str):
        return field
    return field.split(":", 1)[0]


def get_model_schema(schema_cache: dict, model: str):
    if not model:
        return None

    if model in schema_cache:
        return schema_cache.get(model)

    schema = get_schema(models=[model])

    if not isinstance(schema, dict) or "error" in schema:
        schema_cache[model] = None
        return None

    model_info = schema.get(model)
    if not isinstance(model_info, dict):
        schema_cache[model] = None
        return None

    schema_cache[model] = model_info
    return model_info


def field_type(model_info: dict, field_name: str):
    if not isinstance(model_info, dict):
        return None
    fields = model_info.get("fields") or {}
    info = fields.get(field_name) or {}
    return info.get("type")


def is_numeric_field(model_info: dict, field_name: str) -> bool:
    return field_type(model_info, field_name) in NUMERIC_TYPES


def parse_agg_field(field_expr: str):
    if not isinstance(field_expr, str):
        return None, None

    m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*):(sum|avg|min|max|count)$", field_expr.strip())
    if not m:
        return None, None

    return m.group(1), m.group(2)


def normalize_orderby(orderby: str):
    if not isinstance(orderby, str):
        return orderby

    value = orderby.strip()

    if value in ORDERBY_COUNT_VALUES:
        return value

    m = re.match(r"^(sum|avg|min|max|count)\(([^)]+)\)\s+(asc|desc)$", value, re.IGNORECASE)
    if m:
        _agg, field_name, direction = m.groups()
        return f"{field_name.strip()} {direction.lower()}"

    m2 = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*):(sum|avg|min|max|count)\s+(asc|desc)$", value, re.IGNORECASE)
    if m2:
        field_name, _agg, direction = m2.groups()
        return f"{field_name.strip()} {direction.lower()}"

    # Permite alias comunes de agregación: amount_total_sum desc -> amount_total desc
    m3 = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)_(sum|avg|min|max|count)\s+(asc|desc)$", value, re.IGNORECASE)
    if m3:
        field_name, _agg, direction = m3.groups()
        return f"{field_name.strip()} {direction.lower()}"

    return value


def extract_orderby_field(orderby: str):
    if not isinstance(orderby, str):
        return None

    value = orderby.strip()
    if not value:
        return None

    return value.split()[0]


def validate_against_schema(schema, model, fields=None, groupby=None, domain=None, orderby=None):
    if not isinstance(schema, dict) or not model:
        return None

    model_info = schema.get(model)
    if not model_info:
        return None

    model_fields = model_info.get("fields") or {}
    invalid = []

    if fields:
        for f in fields:
            if not isinstance(f, str):
                invalid.append(str(f))
                continue

            base = base_field(f)

            if base not in model_fields:
                invalid.append(base)
                continue

            if ":" in f:
                agg_base, agg_func = parse_agg_field(f)

                if not agg_base or not agg_func:
                    invalid.append(f)
                    continue

                ftype = model_fields[agg_base].get("type")

                if agg_func in {"sum", "avg", "min", "max"} and ftype not in NUMERIC_TYPES:
                    invalid.append(f)

    if groupby:
        for f in groupby:
            if not isinstance(f, str):
                invalid.append(str(f))
                continue

            base = base_field(f)
            if base not in model_fields:
                invalid.append(base)

    if domain:
        for f in field_names_from_domain(domain):
            base = f.split(".")[0]
            if base not in model_fields:
                invalid.append(f)

    if orderby and isinstance(orderby, str):
        normalized_orderby = normalize_orderby(orderby)

        if normalized_orderby not in ORDERBY_COUNT_VALUES:
            ob_field = extract_orderby_field(normalized_orderby)

            if ob_field and ob_field != "__count":
                if ob_field not in model_fields:
                    invalid.append(f"orderby:{ob_field}")

    if invalid:
        unique = sorted(set(invalid))
        return f"Campos inválidos o agregaciones no permitidas en {model}: {unique}"

    return None
