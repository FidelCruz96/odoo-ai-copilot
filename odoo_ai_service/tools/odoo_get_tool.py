import os
import logging
import requests
import re
odoo_base_url = os.getenv("ODOO_BASE_URL") or os.getenv("ODOO_URL") or "http://web:8069"
odoo_db = os.getenv("ODOO_DB")
odoo_ai_token = os.getenv("ODOO_AI_TOKEN")
ODOO_API = f"{odoo_base_url}/ai/get_data"
ODOO_SCHEMA_API = f"{odoo_base_url}/ai/schema"

logger = logging.getLogger("odoo_ai_service")

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

    if domain is not None and not isinstance(domain, list):
        return "invalid_domain_type"

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

        if not isinstance(groupby, list):
            return "invalid_groupby_type"

        has_groupby = len(groupby) > 0
        has_aggregate = _has_valid_aggregate_field(fields)

        # read_group debe tener al menos groupby o agregación válida
        if not has_groupby and not has_aggregate:
            return "group_requires_groupby_or_aggregate"

        if limit is not None and (not isinstance(limit, int) or limit < 1 or limit > 100):
            return "invalid_limit"

    if operation == "search":
        if limit is not None and (not isinstance(limit, int) or limit < 1 or limit > 100):
            return "invalid_limit"

    return None

def query_odoo(model, operation="search_read", domain=None, fields=None, ids=None, groupby=None, orderby=None, limit=None):
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
    logger.info("QUERYING ODOO payload=%s", payload)
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


def get_schema(models, force=False):
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
