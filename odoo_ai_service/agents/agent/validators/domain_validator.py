from __future__ import annotations

from datetime import date, timedelta

OPERATOR_ALIASES = {
    "greater_than": ">",
    "less_than": "<",
    "greater_or_equal": ">=",
    "less_or_equal": "<=",
    "greater_than_or_equal": ">=",
    "less_than_or_equal": "<=",
    "ge": ">=",
    "le": "<=",
    "gt": ">",
    "lt": "<",
}

TODAY_TOKENS = {"today", "hoy"}


def clean_text(value):
    if not isinstance(value, str):
        return value
    return "".join(ch for ch in value if ch.isprintable()).strip()


def normalize_domain_operators(domain):
    if not isinstance(domain, list):
        return domain

    normalized = []
    for item in domain:
        if isinstance(item, (list, tuple)) and len(item) == 3:
            field, operator, value = item
            if operator in OPERATOR_ALIASES:
                operator = OPERATOR_ALIASES[operator]
            normalized.append([field, operator, value])
        else:
            normalized.append(item)

    return normalized


def _is_numeric_id_string(value):
    return isinstance(value, str) and value.isdigit()


def _is_id_like_field(field_name):
    if not isinstance(field_name, str):
        return False
    return field_name == "id" or field_name.endswith("_id") or field_name.endswith(".id")


def _coerce_bool_literal(value):
    if not isinstance(value, str):
        return value
    lower = value.strip().lower()
    if lower == "false":
        return False
    if lower == "true":
        return True
    return value


def _today_range_clauses(field_name):
    today = date.today()
    tomorrow = today + timedelta(days=1)
    return [[field_name, ">=", str(today)], [field_name, "<", str(tomorrow)]]


def normalize_domain_values(domain):
    if not isinstance(domain, list):
        return domain

    normalized = []
    for clause in domain:
        if isinstance(clause, (list, tuple)) and len(clause) == 2:
            field, token = clause
            if isinstance(field, str) and isinstance(token, str) and token.strip().lower() in TODAY_TOKENS:
                normalized.extend(_today_range_clauses(field))
                continue
            normalized.append(list(clause))
            continue

        if not (isinstance(clause, (list, tuple)) and len(clause) == 3):
            normalized.append(clause)
            continue

        field, operator, value = clause

        if isinstance(operator, str) and operator.strip().lower() in TODAY_TOKENS:
            normalized.extend(_today_range_clauses(field))
            continue

        if isinstance(value, list):
            value = [_coerce_bool_literal(v) for v in value]
        else:
            value = _coerce_bool_literal(value)

        normalized.append([field, operator, value])

    return normalized


def coerce_domain_id_values(domain):
    if not isinstance(domain, list):
        return domain

    coerced = []
    for clause in domain:
        if not (isinstance(clause, (list, tuple)) and len(clause) == 3):
            coerced.append(clause)
            continue

        field, operator, value = clause
        if _is_id_like_field(field):
            if operator in ("=", "!=") and _is_numeric_id_string(value):
                value = int(value)
            elif operator in ("in", "not in") and isinstance(value, list):
                value = [int(v) if _is_numeric_id_string(v) else v for v in value]
        coerced.append([field, operator, value])

    return coerced


def validate_domain(domain: list) -> list:
    VALID_OPERATORS = {"=", "!=", ">", ">=", "<", "<=", "like", "ilike", "in", "not in", "child_of"}
    LOGICAL_OPS = {"&", "|", "!"}
    validated = []

    for clause in domain:
        if isinstance(clause, str) and clause in LOGICAL_OPS:
            validated.append(clause)
            continue

        if not isinstance(clause, (list, tuple)) or len(clause) != 3:
            raise ValueError(
                f"Cláusula de dominio inválida: {clause}. "
                "Se esperan EXACTAMENTE 3 elementos (field, operator, value), "
                f"se recibieron {len(clause) if isinstance(clause, (list, tuple)) else type(clause)}."
            )

        field, operator, value = clause

        if isinstance(operator, str):
            if operator == "&lt;=":
                operator = "<="
            elif operator == "&gt;=":
                operator = ">="
            elif operator == "&lt;":
                operator = "<"
            elif operator == "&gt;":
                operator = ">"

        if operator not in VALID_OPERATORS:
            raise ValueError(
                f"Operador inválido '{operator}' en {clause}. "
                f"Operadores válidos: {sorted(VALID_OPERATORS)}"
            )

        validated.append([field, operator, value])

    return validated
