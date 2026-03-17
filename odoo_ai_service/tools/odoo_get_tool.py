import os
import logging
import requests

odoo_base_url = os.getenv("ODOO_BASE_URL") or os.getenv("ODOO_URL") or "http://web:8069"
odoo_db = os.getenv("ODOO_DB")
odoo_ai_token = os.getenv("ODOO_AI_TOKEN")
ODOO_API = f"{odoo_base_url}/ai/get_data"
ODOO_SCHEMA_API = f"{odoo_base_url}/ai/schema"

logger = logging.getLogger("odoo_ai_service")

def query_odoo(model, operation="search_read", domain=None, fields=None, ids=None, groupby=None, orderby=None, limit=None):

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
    print("QUERYING ODOO:", payload)
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


def get_schema(force=False, models=None):
    payload = {"jsonrpc": "2.0", "method": "call", "params": {}, "id": 1}
    if force:
        payload["params"]["force"] = True
    if models:
        payload["params"]["models"] = models

    params = {"db": odoo_db} if odoo_db else None
    headers = {}
    if odoo_ai_token:
        headers["X-AI-Token"] = odoo_ai_token

    response = requests.post(ODOO_SCHEMA_API, params=params, json=payload, headers=headers, timeout=30)
    if not response.ok:
        logger.error("odoo_get_schema status=%s body=%s", response.status_code, response.text)
        return {"error": f"odoo_http_{response.status_code}"}

    try:
        data = response.json()
    except Exception:
        logger.exception("odoo_get_schema response not JSON: %s", response.text)
        return {"error": "odoo_non_json_response"}

    result = data.get("result", data) if isinstance(data, dict) else data
    return result
