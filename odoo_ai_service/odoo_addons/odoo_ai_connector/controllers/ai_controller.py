from __future__ import annotations

import json
import os

from odoo import SUPERUSER_ID, http
from odoo.http import request


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

MAX_QUERY_LIMIT = int(os.getenv("ODOO_AI_MAX_QUERY_LIMIT", "100"))


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _json_response(payload: dict, status: int = 200):
    return request.make_json_response(payload, status=status)


def _get_json_payload() -> dict:
    raw_payload = request.httprequest.get_data(cache=False, as_text=True) or ""
    if not raw_payload.strip():
        return {}
    try:
        return json.loads(raw_payload)
    except json.JSONDecodeError:
        return {}


def _check_token():
    require_token = _bool_env("AI_REQUIRE_SERVICE_TOKEN", default=True)
    expected_token = os.getenv("AI_SERVICE_TOKEN")
    provided_token = request.httprequest.headers.get("X-AI-Token")
    if not require_token:
        return None
    if not expected_token or provided_token != expected_token:
        return _json_response({"error": "unauthorized"}, status=401)
    return None


def _get_request_db() -> str | None:
    return request.httprequest.args.get("db") or request.session.db


def _get_env():
    db_name = _get_request_db()
    if not db_name:
        return None, _json_response({"error": "db_required"}, status=400)
    request.session.db = db_name
    return request.env(user=SUPERUSER_ID), None


def _normalize_field_name(field_expr) -> str | None:
    if not isinstance(field_expr, str):
        return None
    raw_field = field_expr.strip()
    if not raw_field:
        return None
    if ":" in raw_field:
        return raw_field.split(":", 1)[0].strip()
    return raw_field


def _has_blocked_fields(values) -> bool:
    if not isinstance(values, list):
        return False
    for value in values:
        field_name = _normalize_field_name(value)
        if field_name and field_name.lower() in BLOCKED_FIELDS:
            return True
    return False


def _validate_model(model: str) -> str | None:
    if not isinstance(model, str) or not model:
        return "model_required"
    if model not in ALLOWED_MODELS:
        return "model_not_allowed"
    return None


def _validate_common_params(params: dict) -> str | None:
    model_error = _validate_model(params.get("model"))
    if model_error:
        return model_error

    limit = params.get("limit")
    if limit is not None and (not isinstance(limit, int) or limit < 1 or limit > MAX_QUERY_LIMIT):
        return "invalid_limit"

    domain = params.get("domain")
    if domain is not None and not isinstance(domain, list):
        return "invalid_domain_type"

    fields = params.get("fields")
    if fields is not None and not isinstance(fields, list):
        return "invalid_fields_type"
    if _has_blocked_fields(fields):
        return "blocked_field_requested"

    groupby = params.get("groupby")
    if groupby is not None and not isinstance(groupby, list):
        return "invalid_groupby_type"
    if _has_blocked_fields(groupby):
        return "blocked_field_requested"

    return None


class OdooAIConnectorController(http.Controller):
    @http.route("/ai/get_data", type="http", auth="none", methods=["POST"], csrf=False, save_session=False)
    def get_data(self, **kwargs):
        auth_error = _check_token()
        if auth_error:
            return auth_error

        env, env_error = _get_env()
        if env_error:
            return env_error

        payload = _get_json_payload()
        params = payload.get("params") if isinstance(payload, dict) else {}
        if not isinstance(params, dict):
            return _json_response({"error": "invalid_params"}, status=400)

        validation_error = _validate_common_params(params)
        if validation_error:
            return _json_response({"error": validation_error}, status=400)

        model_name = params["model"]
        model = env[model_name].sudo()
        operation = params.get("operation", "search_read")
        domain = params.get("domain") or []
        fields = params.get("fields") or []
        ids = params.get("ids") or []
        groupby = params.get("groupby") or []
        orderby = params.get("orderby")
        limit = params.get("limit")

        try:
            if operation == "search":
                result = model.search(domain, limit=limit, order=orderby).ids
            elif operation == "search_count":
                result = model.search_count(domain)
            elif operation == "read":
                if not isinstance(ids, list) or not ids:
                    return _json_response({"error": "read_requires_ids"}, status=400)
                if not fields:
                    return _json_response({"error": "read_requires_fields"}, status=400)
                result = model.browse(ids).read(fields)
            elif operation == "read_group":
                if not fields:
                    return _json_response({"error": "group_requires_fields"}, status=400)
                result = model.read_group(domain, fields, groupby, offset=0, limit=limit, orderby=orderby, lazy=False)
            else:
                return _json_response({"error": "operation_not_allowed"}, status=400)
        except Exception as exc:
            return _json_response({"error": "odoo_execution_error", "detail": str(exc)}, status=500)

        return _json_response({"result": result})

    @http.route("/ai/schema", type="http", auth="none", methods=["POST"], csrf=False, save_session=False)
    def get_schema(self, **kwargs):
        auth_error = _check_token()
        if auth_error:
            return auth_error

        env, env_error = _get_env()
        if env_error:
            return env_error

        payload = _get_json_payload()
        params = payload.get("params") if isinstance(payload, dict) else {}
        if not isinstance(params, dict):
            return _json_response({"error": "invalid_params"}, status=400)

        models = params.get("models")
        if not isinstance(models, list) or not models:
            return _json_response({"error": "models_required"}, status=400)
        if any(_validate_model(model) for model in models):
            return _json_response({"error": "model_not_allowed"}, status=400)

        response = {}
        try:
            for model_name in models:
                model = env[model_name].sudo()
                fields_meta = model.fields_get()
                response[model_name] = {
                    "name": getattr(model, "_description", model_name),
                    "fields": {
                        field_name: {
                            "type": field_info.get("type"),
                            "relation": field_info.get("relation"),
                            "store": field_info.get("store"),
                        }
                        for field_name, field_info in fields_meta.items()
                        if field_name.lower() not in BLOCKED_FIELDS
                    },
                }
        except Exception as exc:
            return _json_response({"error": "odoo_execution_error", "detail": str(exc)}, status=500)

        return _json_response({"result": response})
