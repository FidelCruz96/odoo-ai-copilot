from __future__ import annotations

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
