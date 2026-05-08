import os
import logging
import requests
import re

odoo_base_url = os.getenv("ODOO_BASE_URL") or os.getenv("ODOO_URL") or "http://web:8069"
odoo_db = os.getenv("ODOO_DB")
odoo_ai_token = os.getenv("ODOO_AI_TOKEN")
ODOO_API = f"{odoo_base_url}/ai/get_data"
ODOO_SCHEMA_API = f"{odoo_base_url}/ai/schema"
MAX_QUERY_LIMIT = int(os.getenv("ODOO_AI_MAX_QUERY_LIMIT", "100"))

ALLOWED_MODELS = {
    "sale.order",
    "sale.order.line",
    "account.move",
    "account.move.line",
    "purchase.order",
    "purchase.order.line",
    "res.partner",
    "product.product",
    "stock.picking",
}

BLOCKED_FIELDS = {
    "password",
    "token",
    "api_key",
    "access_token",
    "secret",
}

logger = logging.getLogger("odoo_ai_service")


def _build_access_context(context):
    if not isinstance(context, dict):
        return {}

    access_context = context.get("access_context") or context.get("security")
    if not isinstance(access_context, dict):
        user = context.get("user") if isinstance(context.get("user"), dict) else {}
        company = context.get("company") if isinstance(context.get("company"), dict) else {}
        access_context = {
            "uid": user.get("id") or user.get("uid"),
            "user_id": user.get("id") or user.get("uid"),
            "company_id": company.get("id"),
            "active_company_id": company.get("id"),
            "company_ids": company.get("company_ids") or company.get("allowed_company_ids"),
            "allowed_company_ids": company.get("company_ids") or company.get("allowed_company_ids"),
            "lang": context.get("lang"),
            "tz": context.get("tz"),
        }

    clean = dict(access_context)
    if context.get("request_id") and not clean.get("request_id"):
        clean["request_id"] = context.get("request_id")
    return clean


def _normalize_field_name(field_expr):
    if not isinstance(field_expr, str):
        return None
    raw_field = field_expr.strip()
    if not raw_field:
        return None
    base_field, _agg = _parse_agg_field(raw_field)
    if base_field:
        return base_field
    return raw_field


def _is_allowed_model(model):
    return isinstance(model, str) and model in ALLOWED_MODELS


def _has_blocked_field(entries):
    if not isinstance(entries, list):
        return False
    for entry in entries:
        field_name = _normalize_field_name(entry)
        if field_name and field_name.lower() in BLOCKED_FIELDS:
            return True
    return False

def _parse_agg_field(field_expr: str):
    """
    Acepta solo formatos válidos tipo:
    - amount_total:sum
    - product_uom_qty:avg
    - id:count

    Devuelve (base_field, agg_func) o (None, None)
    """
    if not isinstance(field_expr, str):
        return None, None

    m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*):(sum|avg|min|max|count)$", field_expr.strip())
    if not m:
        return None, None

    return m.group(1), m.group(2)


def _has_valid_aggregate_field(fields):
    if not isinstance(fields, list):
        return False

    for f in fields:
        if not isinstance(f, str):
            continue
        agg_base, agg_func = _parse_agg_field(f)
        if agg_base and agg_func:
            return True
    return False


def _validate_query_payload(operation, model, domain=None, fields=None, ids=None, groupby=None, orderby=None, limit=None):
    if not model or not isinstance(model, str):
        return "model_required"
    if not _is_allowed_model(model):
        return "model_not_allowed"

    if domain is not None and not isinstance(domain, list):
        return "invalid_domain_type"
    if fields is not None and not isinstance(fields, list):
        return "invalid_fields_type"
    if groupby is not None and not isinstance(groupby, list):
        return "invalid_groupby_type"
    if _has_blocked_field(fields):
        return "blocked_field_requested"
    if _has_blocked_field(groupby):
        return "blocked_field_requested"
    if limit is not None and (not isinstance(limit, int) or limit < 1 or limit > MAX_QUERY_LIMIT):
        return "invalid_limit"

    if operation == "read":
        if not ids or not isinstance(ids, list):
            return "read_requires_ids"
        if not fields or not isinstance(fields, list):
            return "read_requires_fields"

    if operation == "read_group":
        if not fields or not isinstance(fields, list):
            return "group_requires_fields"

        if groupby is None:
            groupby = []

        has_groupby = len(groupby) > 0
        has_aggregate = _has_valid_aggregate_field(fields)

        # read_group debe tener al menos groupby o agregación válida
        if not has_groupby and not has_aggregate:
            return "group_requires_groupby_or_aggregate"

    return None

def query_odoo(model, operation="search_read", domain=None, fields=None, ids=None, groupby=None, orderby=None, limit=None, context=None):
    validation_error = _validate_query_payload(operation, model, domain, fields, ids, groupby, orderby, limit)
    if validation_error:
        return {"error": validation_error}
    payload = {
        "model": model,
        "operation": operation,
        "domain": domain or [],
        "fields": fields or [],
    }
    if ids is not None:
        payload["ids"] = ids
    if groupby is not None:
        payload["groupby"] = groupby
    if orderby is not None:
        payload["orderby"] = orderby
    if limit is not None:
        payload["limit"] = limit
    access_context = _build_access_context(context)
    if access_context:
        payload["access_context"] = access_context
    elif os.getenv("ODOO_AI_REQUIRE_ACCESS_CONTEXT", "true").strip().lower() in {"1", "true", "yes", "y", "on"}:
        return {"error": "access_context_required"}
    logger.info(
        "QUERYING ODOO model=%s operation=%s fields=%s groupby=%s limit=%s uid=%s",
        model,
        operation,
        fields or [],
        groupby or [],
        limit,
        access_context.get("uid") or access_context.get("user_id"),
    )
    rpc_payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": payload,
        "id": 1
    }
    params = {"db": odoo_db} if odoo_db else None
    headers = {}
    if odoo_ai_token:
        headers["X-AI-Token"] = odoo_ai_token
    response = requests.post(ODOO_API, params=params, json=rpc_payload, headers=headers, timeout=20)
    if not response.ok:
        logger.error("odoo_get_tool status=%s body=%s", response.status_code, response.text)
        return {"error": f"odoo_http_{response.status_code}"}

    try:
        data = response.json()
    except Exception:
        logger.exception("odoo_get_tool response not JSON: %s", response.text)
        return {"error": "odoo_non_json_response"}

    # Odoo controller returns JSON via make_json_response(result)
    # which can be either a dict (with "result") or a raw list.
    result = data.get("result", data) if isinstance(data, dict) else data
    try:
        if isinstance(result, list):
            logger.info("odoo_get_tool result list size=%s sample=%s", len(result), result[:2])
        else:
            logger.info("odoo_get_tool result type=%s sample=%s", type(result).__name__, str(result)[:500])
    except Exception:
        logger.exception("odoo_get_tool result log failed")

    return result


def get_schema(models, force=False, context=None):
    """
    Obtiene un schema resumido de Odoo solo para los modelos solicitados.

    Retorna un dict con esta forma:
    {
        "sale.order": {
            "name": "Sales Order",
            "fields": {
                "date_order": {"type": "datetime", "relation": None, "store": True},
                "user_id": {"type": "many2one", "relation": "res.users", "store": True},
                ...
            }
        }
    }
    """
    if not models or not isinstance(models, list):
        return {"error": "models_required"}
    if not all(_is_allowed_model(model) for model in models):
        return {"error": "model_not_allowed"}

    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "models": models,
        },
        "id": 1,
    }

    if force:
        payload["params"]["force"] = True
    access_context = _build_access_context(context)
    if access_context:
        payload["params"]["access_context"] = access_context
    elif os.getenv("ODOO_AI_REQUIRE_ACCESS_CONTEXT", "true").strip().lower() in {"1", "true", "yes", "y", "on"}:
        return {"error": "access_context_required"}

    params = {"db": odoo_db} if odoo_db else None
    headers = {}
    if odoo_ai_token:
        headers["X-AI-Token"] = odoo_ai_token

    try:
        response = requests.post(
            ODOO_SCHEMA_API,
            params=params,
            json=payload,
            headers=headers,
            timeout=15,
        )
    except requests.RequestException as e:
        logger.exception("odoo_get_schema request error")
        return {"error": f"odoo_request_error: {e}"}

    if not response.ok:
        logger.error("odoo_get_schema status=%s body=%s", response.status_code, response.text)
        return {"error": f"odoo_http_{response.status_code}"}

    try:
        data = response.json()
    except Exception:
        logger.exception("odoo_get_schema response not JSON: %s", response.text)
        return {"error": "odoo_non_json_response"}

    result = data.get("result", data) if isinstance(data, dict) else data
    if not isinstance(result, dict):
        return {"error": "odoo_invalid_schema_format"}

    filtered = {}

    for model in models:
        model_info = result.get(model)
        if not isinstance(model_info, dict):
            continue

        raw_fields = model_info.get("fields") or {}
        clean_fields = {}

        for field_name, field_info in raw_fields.items():
            if not isinstance(field_info, dict):
                continue

            clean_fields[field_name] = {
                "type": field_info.get("type"),
                "relation": field_info.get("relation"),
                "store": field_info.get("store"),
            }

        filtered[model] = {
            "name": model_info.get("name"),
            "fields": clean_fields,
        }

    if not filtered:
        return {"error": "schema_models_not_found"}

    return filtered
