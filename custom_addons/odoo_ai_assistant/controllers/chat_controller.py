import os
import logging
import requests
from requests.exceptions import RequestException
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://ai_service:8000/ask")
# Memoria (historial) configurables
def _get_history_settings():
    params = request.env["ir.config_parameter"].sudo()
    limit_raw = params.get_param("odoo_ai_assistant.ai_chat_history_limit", "8")
    use_raw = params.get_param("odoo_ai_assistant.ai_chat_use_server_history", "True")
    try:
        limit = int(limit_raw)
    except Exception:
        limit = 8
    use_server = str(use_raw).lower() in ("1", "true", "yes", "y", "on")
    return limit, use_server
# AI_SERVICE_TOKEN = os.getenv("AI_SERVICE_TOKEN")
# ODOO_AI_TOKEN = os.getenv("ODOO_AI_TOKEN")
# AI_ALLOWED_MODELS = set(
#     m.strip() for m in os.getenv(
#         "AI_ALLOWED_MODELS",
#         "res.partner,sale.order,product.product,account.move"
#     ).split(",") if m.strip()
# )
# AI_BLOCKED_FIELDS = set(
#     f.strip() for f in os.getenv(
#         "AI_BLOCKED_FIELDS",
#         "password,api_key,access_token,client_secret,oauth_token"
#     ).split(",") if f.strip()
# )
# AI_MAX_LIMIT = int(os.getenv("AI_MAX_LIMIT", "200"))
# AI_ALLOWED_OPERATIONS = {"search_read", "search", "read", "read_group"}


def _validate_domain(domain):
    if domain is None:
        return []

    if not isinstance(domain, list):
        raise ValueError("Domain debe ser una lista.")

    valid_ops = {"=", "!=", ">", ">=", "<", "<=", "like", "ilike", "in", "not in", "child_of"}
    logical_ops = {"&", "|", "!"}
    validated = []

    for clause in domain:
        if isinstance(clause, str) and clause in logical_ops:
            validated.append(clause)
            continue

        if not isinstance(clause, (list, tuple)) or len(clause) != 3:
            raise ValueError(f"Cláusula de dominio inválida: {clause}. Se esperan 3 elementos.")

        field, operator, value = clause
        if operator not in valid_ops:
            raise ValueError(f"Operador inválido '{operator}' en {clause}.")

        validated.append([field, operator, value])

    return validated


def _clamp_limit(limit):
    if limit is None:
        return None
    try:
        limit = int(limit)
    except Exception:
        return None
    if limit <= 0:
        return None
    return limit


def _require_service_token():
    return None


def _get_session_key(client_context):
    if not isinstance(client_context, dict):
        return None
    session_key = client_context.get("chat_session_key")
    if not session_key:
        return None
    return str(session_key).strip() or None


def _get_memory_store():
    return request.env["ai.chat.session.memory"].sudo()


def _get_session_memory(user_id, session_key):
    if not session_key:
        return {}
    return _get_memory_store().get_memory_for_user_session(user_id, session_key)


def _save_session_memory(user_id, session_key, memory):
    if not session_key or not isinstance(memory, dict):
        return
    _get_memory_store().save_memory_for_user_session(user_id, session_key, memory)


class AIChatController(http.Controller):

    @http.route("/ai_assistant/ask", type="json", auth="user")
    def ask(self, question, context=None):
        ai_url = AI_SERVICE_URL
        _logger.info("AI ask (json) question=%s", question)
        user = request.env.user
        company = request.env.company
        ctx = request.context or {}
        session_key = _get_session_key(context or {})
        memory = _get_session_memory(user.id, session_key)
        history = []
        history_limit, use_server_history = _get_history_settings()
        if use_server_history and history_limit > 0:
            history = request.env["ai.chat"].sudo().search(
                [("user_id", "=", user.id), ("session_key", "=", session_key)] if session_key else [("user_id", "=", user.id)],
                order="create_date desc",
                limit=history_limit,
            )
        history_payload = []
        for h in reversed(history):
            if h.question:
                history_payload.append({"role": "user", "text": h.question, "source": "server"})
            if h.answer:
                history_payload.append({"role": "bot", "text": h.answer, "source": "server"})

        payload = {
            "question": question,
            "context": {
                "user": {"id": user.id, "name": user.name},
                "company": {"id": company.id, "name": company.name},
                "lang": ctx.get("lang"),
                "tz": ctx.get("tz"),
                "client": context or {},
                "memory": memory,
                "history_limit": history_limit,
                "use_server_history": use_server_history,
                "history_server": history_payload,
            },
        }
        try:
            response = requests.post(ai_url, json=payload, timeout=20)
        except RequestException:
            _logger.exception("AI ask (json) request failed")
            return {"answer": "No pude conectar con el servicio de IA. Intenta nuevamente."}
        _logger.info("AI ask (json) status=%s body=%s", response.status_code, response.text)

        answer = ""
        memory_response = None
        try:
            result = response.json()
            answer = result.get("answer", "")
            memory_response = result.get("memory")
        except Exception:
            _logger.exception("AI ask (json) response is not JSON")
            answer = "Ocurrió un error al procesar la respuesta del servicio de IA."

        _save_session_memory(user.id, session_key, memory_response)

        request.env["ai.chat"].sudo().create({
            "user_id": request.env.user.id,
            "session_key": session_key,
            "question": question,
            "answer": answer
        })

        return {"answer": answer}

    @http.route("/ai_assistant/ask_http", type="http", auth="user", csrf=False, methods=["POST"])
    def ask_http(self, **kwargs):
        data = request.httprequest.get_json(silent=True) or {}
        question = data.get("question") or ""
        client_context = data.get("context") or {}
        if not question:
            return request.make_json_response({"answer": ""})

        ai_url = AI_SERVICE_URL
        _logger.info("AI ask_http question=%s", question)
        user = request.env.user
        company = request.env.company
        ctx = request.context or {}
        session_key = _get_session_key(client_context)
        memory = _get_session_memory(user.id, session_key)
        history = []
        history_limit, use_server_history = _get_history_settings()
        if use_server_history and history_limit > 0:
            history = request.env["ai.chat"].sudo().search(
                [("user_id", "=", user.id), ("session_key", "=", session_key)] if session_key else [("user_id", "=", user.id)],
                order="create_date desc",
                limit=history_limit,
            )
        history_payload = []
        for h in reversed(history):
            if h.question:
                history_payload.append({"role": "user", "text": h.question, "source": "server"})
            if h.answer:
                history_payload.append({"role": "bot", "text": h.answer, "source": "server"})
        payload = {
            "question": question,
            "context": {
                "user": {"id": user.id, "name": user.name},
                "company": {"id": company.id, "name": company.name},
                "lang": ctx.get("lang"),
                "tz": ctx.get("tz"),
                "client": client_context,
                "memory": memory,
                "history_limit": history_limit,
                "use_server_history": use_server_history,
                "history_server": history_payload,
            },
        }
        try:
            response = requests.post(ai_url, json=payload, timeout=60)
        except RequestException:
            _logger.exception("AI ask_http request failed")
            return request.make_json_response({"answer": "No pude conectar con el servicio de IA. Intenta nuevamente."})
        _logger.info("AI ask_http status=%s body=%s", response.status_code, response.text)

        answer = ""
        memory_response = None
        try:
            result = response.json()
            answer = result.get("answer", "")
            memory_response = result.get("memory")
        except Exception:
            _logger.exception("AI ask_http response is not JSON")
            answer = "Ocurrió un error al procesar la respuesta del servicio de IA."

        _save_session_memory(user.id, session_key, memory_response)

        request.env["ai.chat"].sudo().create({
            "user_id": request.env.user.id,
            "session_key": session_key,
            "question": question,
            "answer": answer
        })

        return request.make_json_response({"answer": answer})


class AIController(http.Controller):

    @http.route("/ai/get_data", type="http", auth="public", csrf=False, methods=["POST"])
    def ai_query(self, **kwargs):
        payload = request.httprequest.get_json(silent=True) or {}
        params = payload.get("params", payload)

        model = params.get("model")
        operation = params.get("operation", "search_read")
        domain = params.get("domain") or []
        fields = params.get("fields") or []
        ids = params.get("ids") or []
        groupby = params.get("groupby") or []
        orderby = params.get("orderby")
        limit = _clamp_limit(params.get("limit"))

        if not model:
            return request.make_json_response({"error": "missing model"})

        try:
            domain = _validate_domain(domain)
            Model = request.env[model].sudo()

            if operation == "search_read":
                result = Model.search_read(domain, fields, limit=limit)
            elif operation == "search":
                result = Model.search(domain, limit=limit).ids
            elif operation == "search_count":
                result = Model.search_count(domain)
            elif operation == "read":
                result = Model.browse(ids).read(fields)
            elif operation == "read_group":
                result = Model.read_group(domain, fields, groupby, orderby=orderby, limit=limit)
            else:
                result = {"error": "operation not supported"}

            return request.make_json_response(result)
        except Exception as e:
            _logger.exception("AI query error")
            return request.make_json_response({"error": str(e)})

    @http.route("/ai/schema", type="http", auth="public", csrf=False, methods=["GET", "POST"])
    def ai_schema(self, **kwargs):
        payload = request.httprequest.get_json(silent=True) or {}
        params = payload.get("params", payload) if isinstance(payload, dict) else {}
        force = bool(params.get("force")) if isinstance(params, dict) else False
        models_filter = params.get("models") if isinstance(params, dict) else None

        try:
            schema = request.env["ai.schema.cache"].sudo().get_schema(
                force=force,
                models_filter=models_filter,
            )
            return request.make_json_response(schema)
        except Exception as e:
            _logger.exception("AI schema error")
            return request.make_json_response({"error": str(e)})
