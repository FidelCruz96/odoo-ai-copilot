from __future__ import annotations

from odoo import http
from odoo.http import request

from .chat_controller import (
    AI_ALLOWED_OPERATIONS,
    _clamp_limit,
    _error_response,
    _normalize_operation,
    _require_service_token,
    _sanitize_schema_payload,
    _validate_domain,
    _validate_fields,
    _validate_groupby,
    _validate_ids,
    _validate_model_name,
    _validate_orderby,
)


class AIBridgeController(http.Controller):
    @http.route("/ai/get_data", type="http", auth="public", csrf=False, methods=["POST"])
    def ai_query_bridge(self, **kwargs):
        auth_error = _require_service_token()
        if auth_error:
            return auth_error

        payload = request.httprequest.get_json(silent=True) or {}
        params = payload.get("params", payload) if isinstance(payload, dict) else {}
        if not isinstance(params, dict):
            return _error_response("ERR_INVALID_PAYLOAD", "Payload inválido.")

        model = params.get("model")
        operation = _normalize_operation(params.get("operation", "search_read"))
        domain = params.get("domain") or []
        fields = params.get("fields") or []
        ids = params.get("ids") or []
        groupby = params.get("groupby") or []
        orderby = params.get("orderby")

        try:
            model = _validate_model_name(model)
            if operation not in AI_ALLOWED_OPERATIONS:
                return _error_response("ERR_OPERATION_NOT_ALLOWED", "Operación no permitida.", status=403)

            domain = _validate_domain(domain, model_name=model)
            fields = _validate_fields(fields)
            ids = _validate_ids(ids)
            groupby = _validate_groupby(groupby)
            orderby = _validate_orderby(orderby)
            limit = _clamp_limit(params.get("limit"), default=20) if operation in ("search", "search_read", "read_group") else None

            Model = request.env[model].sudo()
            if operation == "search_read":
                result = Model.search_read(domain, fields, limit=limit)
            elif operation == "search":
                result = Model.search(domain, limit=limit).ids
            elif operation == "search_count":
                result = Model.search_count(domain)
            elif operation == "read":
                if not ids:
                    return _error_response("ERR_INVALID_QUERY", "La operación 'read' requiere IDs.")
                if not fields:
                    return _error_response("ERR_INVALID_QUERY", "La operación 'read' requiere campos.")
                result = Model.browse(ids).read(fields)
            elif operation == "read_group":
                if not fields:
                    return _error_response("ERR_INVALID_QUERY", "La operación 'read_group' requiere campos.")
                result = Model.read_group(domain, fields, groupby, orderby=orderby, limit=limit)
            else:
                return _error_response("ERR_OPERATION_NOT_ALLOWED", "Operación no permitida.", status=403)

            return request.make_json_response(result)
        except PermissionError as exc:
            return _error_response("ERR_PERMISSION_DENIED", "Consulta bloqueada por política de seguridad.", status=403, details=exc)
        except ValueError as exc:
            return _error_response("ERR_INVALID_QUERY", "Parámetros de consulta inválidos.", status=400, details=exc)
        except Exception as exc:
            return _error_response("ERR_QUERY_EXECUTION", "No se pudo ejecutar la consulta.", status=500, details=exc)

    @http.route("/ai/schema", type="http", auth="public", csrf=False, methods=["GET", "POST"])
    def ai_schema_bridge(self, **kwargs):
        auth_error = _require_service_token()
        if auth_error:
            return auth_error

        payload = request.httprequest.get_json(silent=True) or {}
        params = payload.get("params", payload) if isinstance(payload, dict) else {}
        models_filter = params.get("models") if isinstance(params, dict) else None
        force = bool(params.get("force")) if isinstance(params, dict) else False

        try:
            schema = request.env["ai.schema.cache"].sudo().get_schema(
                force=force,
                models_filter=models_filter,
            )
        except Exception as exc:
            return _error_response("ERR_SCHEMA", "No se pudo obtener el schema.", status=500, details=exc)

        return request.make_json_response(_sanitize_schema_payload(schema))
