import os
import re
import hmac
import hashlib
import logging
import json
import uuid
from datetime import date, timedelta
import requests
from requests.exceptions import RequestException
from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request

_logger = logging.getLogger(__name__)

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://ai_service:8000/ask")


def _env_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "y", "on")


def _env_int(name, default, min_value=1):
    raw = os.getenv(name)
    try:
        value = int(raw) if raw is not None else int(default)
    except Exception:
        value = int(default)
    if value < min_value:
        return min_value
    return value


def _env_set(name, default=""):
    raw = os.getenv(name, default)
    values = set()
    for chunk in str(raw or "").split(","):
        token = chunk.strip()
        if token:
            values.add(token)
    return values


AI_REQUIRE_SERVICE_TOKEN = _env_bool("AI_REQUIRE_SERVICE_TOKEN", True)
AI_SERVICE_TOKEN = (os.getenv("AI_SERVICE_TOKEN") or os.getenv("ODOO_AI_TOKEN") or "").strip()
AI_ALLOWED_MODELS = _env_set(
    "AI_ALLOWED_MODELS",
    "res.partner,sale.order,sale.order.line,purchase.order,purchase.order.line,"
    "product.product,product.template,account.move,stock.picking,stock.move,stock.quant",
)
AI_BLOCKED_FIELDS = _env_set(
    "AI_BLOCKED_FIELDS",
    "password,password_crypt,api_key,access_token,client_secret,oauth_token,"
    "bank_account,acc_number,token,secret",
)
AI_ALLOWED_OPERATIONS = _env_set(
    "AI_ALLOWED_OPERATIONS",
    "search,search_read,search_count,read,read_group",
)
AI_MAX_LIMIT = _env_int("AI_MAX_LIMIT", 100, min_value=1)
AI_DEFAULT_LIMIT = _env_int("AI_DEFAULT_LIMIT", 20, min_value=1)
AI_MAX_READ_IDS = _env_int("AI_MAX_READ_IDS", 200, min_value=1)
AI_MAX_GROUPBY = _env_int("AI_MAX_GROUPBY", 3, min_value=1)
AI_MAX_FIELDS = _env_int("AI_MAX_FIELDS", 50, min_value=1)
AI_MAX_DOMAIN_CLAUSES = _env_int("AI_MAX_DOMAIN_CLAUSES", 40, min_value=1)
AI_MAX_SCHEMA_MODELS = _env_int("AI_MAX_SCHEMA_MODELS", 25, min_value=1)
AI_RETURN_ERROR_DETAILS = _env_bool("AI_RETURN_ERROR_DETAILS", False)
FIELD_PATH_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*$")
AGG_FIELD_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*:(sum|avg|min|max|count)$")

ENUM_FIELD_VALUES = {
    ("purchase.order", "receipt_status"): {"no", "to_receive", "partial", "full", "2_received", "received"},
    ("account.move", "payment_state"): {"not_paid", "in_payment", "paid", "partial", "reversed", "blocked"},
    ("account.move", "state"): {"draft", "posted", "cancel", "open"},
    ("stock.picking", "state"): {"draft", "waiting", "confirmed", "assigned", "partially_available", "done", "cancel"},
}


def _coerce_literal(value):
    if isinstance(value, str):
        token = value.strip().lower()
        if token == "false":
            return False
        if token == "true":
            return True
    return value


def _expand_today_clause(field):
    today = date.today()
    tomorrow = today + timedelta(days=1)
    return [[field, ">=", str(today)], [field, "<", str(tomorrow)]]


def _validate_enum_values(model_name, field_name, operator, value):
    allowed = ENUM_FIELD_VALUES.get((model_name, field_name))
    if not allowed:
        return

    if operator in ("=", "!="):
        if isinstance(value, str) and value not in allowed:
            raise ValueError(f"valor inválido '{value}' para {model_name}.{field_name}")
        return

    if operator in ("in", "not in") and isinstance(value, list):
        invalid = [v for v in value if isinstance(v, str) and v not in allowed]
        if invalid:
            raise ValueError(f"valores inválidos {invalid} para {model_name}.{field_name}")


def _error_response(error_code, message, status=400, details=None):
    payload = {
        "error_code": error_code,
        "error": message,
    }
    if details and AI_RETURN_ERROR_DETAILS:
        payload["details"] = str(details)
    return request.make_json_response(payload, status=status)


def _normalize_operation(operation):
    if not operation:
        return "search_read"
    return str(operation).strip().lower()


def _validate_model_name(model):
    if not isinstance(model, str) or not model.strip():
        raise ValueError("missing model")
    model = model.strip()
    if not re.match(r"^[a-z][a-z0-9_\.]+$", model):
        raise ValueError("invalid model name")
    if model not in AI_ALLOWED_MODELS:
        raise PermissionError(f"model_not_allowed:{model}")
    return model


def _ensure_field_not_blocked(field_name):
    if not isinstance(field_name, str):
        raise ValueError("invalid field name")
    normalized = field_name.strip().split(":", 1)[0]
    parts = [p for p in normalized.split(".") if p]
    candidates = {normalized}
    if parts:
        candidates.add(parts[0])
        candidates.add(parts[-1])
    for candidate in candidates:
        if candidate in AI_BLOCKED_FIELDS:
            raise PermissionError(f"blocked_field:{candidate}")


def _validate_field_name(field_name):
    if not isinstance(field_name, str):
        raise ValueError("invalid field name")
    field_name = field_name.strip()
    if not field_name:
        raise ValueError("empty field name")
    if not FIELD_PATH_RE.match(field_name):
        raise ValueError(f"invalid field path:{field_name}")
    _ensure_field_not_blocked(field_name)
    return field_name


def _validate_fields(fields):
    if fields is None:
        return []
    if not isinstance(fields, list):
        raise ValueError("fields must be list")
    if len(fields) > AI_MAX_FIELDS:
        raise ValueError("too many fields")
    validated = []
    for field in fields:
        if not isinstance(field, str):
            raise ValueError(f"invalid field:{field}")
        value = field.strip()
        if not value:
            continue
        if ":" in value:
            if not AGG_FIELD_RE.match(value):
                raise ValueError(f"invalid aggregate field:{value}")
            _ensure_field_not_blocked(value.split(":", 1)[0])
            validated.append(value)
        else:
            validated.append(_validate_field_name(value))
    return validated


def _validate_groupby(groupby):
    if groupby is None:
        return []
    if not isinstance(groupby, list):
        raise ValueError("groupby must be list")
    if len(groupby) > AI_MAX_GROUPBY:
        raise ValueError("too many groupby fields")
    return [_validate_field_name(v) for v in groupby]


def _validate_orderby(orderby):
    if orderby in (None, ""):
        return None
    if not isinstance(orderby, str):
        raise ValueError("orderby must be string")
    value = orderby.strip()
    if not value:
        return None
    if len(value) > 200:
        raise ValueError("orderby too long")
    for chunk in value.split(","):
        token = chunk.strip().split()[0] if chunk.strip() else ""
        if not token:
            continue
        if token == "__count":
            continue
        base = token.split(":", 1)[0]
        _validate_field_name(base)
    return value


def _validate_ids(ids):
    if ids is None:
        return []
    if not isinstance(ids, list):
        raise ValueError("ids must be list")
    if len(ids) > AI_MAX_READ_IDS:
        raise ValueError("too many ids")
    validated = []
    for value in ids:
        if isinstance(value, str) and value.isdigit():
            value = int(value)
        if not isinstance(value, int):
            raise ValueError(f"invalid id:{value}")
        validated.append(value)
    return validated


def _sanitize_schema_payload(schema):
    if not isinstance(schema, dict):
        return {}
    clean = {}
    for model_name, model_info in schema.items():
        if not isinstance(model_info, dict):
            continue
        fields = model_info.get("fields")
        if isinstance(fields, dict):
            safe_fields = {}
            for field_name, field_info in fields.items():
                try:
                    _ensure_field_not_blocked(field_name)
                except PermissionError:
                    continue
                safe_fields[field_name] = field_info
            model_copy = dict(model_info)
            model_copy["fields"] = safe_fields
            clean[model_name] = model_copy
        else:
            clean[model_name] = model_info
    return clean
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
def _validate_domain(domain, model_name=None):
    if domain is None:
        return []

    if not isinstance(domain, list):
        raise ValueError("Domain debe ser una lista.")
    if len(domain) > AI_MAX_DOMAIN_CLAUSES:
        raise ValueError("Domain demasiado grande.")

    valid_ops = {"=", "!=", ">", ">=", "<", "<=", "like", "ilike", "in", "not in", "child_of"}
    logical_ops = {"&", "|", "!"}
    validated = []

    for clause in domain:
        if isinstance(clause, str) and clause in logical_ops:
            validated.append(clause)
            continue

        if isinstance(clause, (list, tuple)) and len(clause) == 2:
            field, token = clause
            field = _validate_field_name(field)
            if isinstance(token, str) and token.strip().lower() in {"today", "hoy"}:
                validated.extend(_expand_today_clause(field))
                continue
            raise ValueError(f"Cláusula de dominio inválida: {clause}. Se esperan 3 elementos.")

        if not isinstance(clause, (list, tuple)) or len(clause) != 3:
            raise ValueError(f"Cláusula de dominio inválida: {clause}. Se esperan 3 elementos.")

        field, operator, value = clause
        field = _validate_field_name(field)

        if isinstance(operator, str) and operator.strip().lower() in {"today", "hoy"}:
            validated.extend(_expand_today_clause(field))
            continue

        if operator not in valid_ops:
            raise ValueError(f"Operador inválido '{operator}' en {clause}.")

        if operator in ("in", "not in"):
            if not isinstance(value, list):
                raise ValueError(f"El operador '{operator}' requiere lista en {clause}.")
            if len(value) > AI_MAX_READ_IDS:
                raise ValueError("Lista 'in/not in' demasiado grande.")
            value = [_coerce_literal(v) for v in value]
        else:
            value = _coerce_literal(value)

        if isinstance(model_name, str) and "." not in field:
            _validate_enum_values(model_name, field, operator, value)

        validated.append([field, operator, value])

    return validated

def _clamp_limit(limit, default=None):
    if limit is None:
        return default
    try:
        limit = int(limit)
    except Exception:
        return default
    if limit <= 0:
        return default
    if limit > AI_MAX_LIMIT:
        return AI_MAX_LIMIT
    return limit


def _extract_access_context(params):
    if not isinstance(params, dict):
        return {}
    access_context = params.get("access_context") or params.get("security") or {}
    if isinstance(access_context, dict):
        return access_context
    return {}


def _resolve_ai_user_scope(params):
    access_context = _extract_access_context(params)
    uid = access_context.get("uid") or access_context.get("user_id")
    if isinstance(uid, str) and uid.isdigit():
        uid = int(uid)
    if not isinstance(uid, int):
        raise PermissionError("user_context_required")

    user = request.env["res.users"].sudo().browse(uid).exists()
    if not user or not user.active:
        raise PermissionError("user_context_invalid")

    user_company_ids = set(user.company_ids.ids)
    requested_company_ids = access_context.get("allowed_company_ids") or access_context.get("company_ids")
    if requested_company_ids is None:
        requested_company_ids = [access_context.get("active_company_id") or access_context.get("company_id") or user.company_id.id]
    if not isinstance(requested_company_ids, list):
        requested_company_ids = [requested_company_ids]

    clean_company_ids = []
    for value in requested_company_ids:
        if isinstance(value, str) and value.isdigit():
            value = int(value)
        if isinstance(value, int):
            clean_company_ids.append(value)

    if not clean_company_ids:
        clean_company_ids = [user.company_id.id]

    requested_set = set(clean_company_ids)
    if not requested_set.issubset(user_company_ids):
        raise PermissionError("company_scope_not_allowed")

    active_company_id = access_context.get("active_company_id") or access_context.get("company_id") or clean_company_ids[0]
    if isinstance(active_company_id, str) and active_company_id.isdigit():
        active_company_id = int(active_company_id)
    if active_company_id not in requested_set:
        raise PermissionError("active_company_not_allowed")

    scoped_context = {
        "allowed_company_ids": clean_company_ids,
        "company_id": active_company_id,
    }
    if access_context.get("lang"):
        scoped_context["lang"] = access_context.get("lang")
    if access_context.get("tz"):
        scoped_context["tz"] = access_context.get("tz")

    return user, scoped_context, {
        "uid": user.id,
        "company_ids": clean_company_ids,
        "active_company_id": active_company_id,
        "groups_hash": access_context.get("groups_hash"),
        "request_id": access_context.get("request_id") or params.get("request_id"),
    }


def _scoped_model(model_name, params):
    user, scoped_context, audit_context = _resolve_ai_user_scope(params)
    Model = request.env[model_name].with_user(user.id).with_context(**scoped_context)
    Model.browse().check_access("read")
    return Model, audit_context


def _result_count(result):
    if isinstance(result, list):
        return len(result)
    if isinstance(result, int):
        return result
    if result is None:
        return 0
    return 1


def _log_ai_tool_audit(status, audit_context, model, operation, domain=None, fields=None, result=None, error_code=None):
    audit_context = audit_context or {}
    payload = {
        "status": status,
        "request_id": audit_context.get("request_id"),
        "uid": audit_context.get("uid"),
        "company_ids": audit_context.get("company_ids"),
        "active_company_id": audit_context.get("active_company_id"),
        "groups_hash": audit_context.get("groups_hash"),
        "model": model,
        "operation": operation,
        "domain": domain or [],
        "fields": fields or [],
        "record_count": _result_count(result),
        "error_code": error_code,
    }
    _logger.info("AI_TOOL_AUDIT %s", json.dumps(payload, ensure_ascii=False))


def _require_service_token():
    if not AI_REQUIRE_SERVICE_TOKEN:
        return None

    if not AI_SERVICE_TOKEN:
        _logger.error("AI security misconfigured: missing AI_SERVICE_TOKEN/ODOO_AI_TOKEN")
        return _error_response(
            "ERR_AUTH_NOT_CONFIGURED",
            "Servicio IA no configurado para autenticación.",
            status=503,
        )

    provided = request.httprequest.headers.get("X-AI-Token")
    if not provided or not hmac.compare_digest(str(provided), str(AI_SERVICE_TOKEN)):
        return _error_response(
            "ERR_UNAUTHORIZED",
            "No autorizado.",
            status=401,
        )
    return None


def _ai_service_headers():
    if not AI_SERVICE_TOKEN:
        return {}
    return {"X-AI-Service-Token": AI_SERVICE_TOKEN}


def _hash_groups(group_xmlids):
    raw = ",".join(sorted(str(item) for item in (group_xmlids or []) if item))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest() if raw else None


def _group_xmlids_for_user(user):
    group_xmlids = []
    try:
        external_ids = user.groups_id.get_external_id()
    except Exception:
        external_ids = {}
    for group in user.groups_id:
        xmlid = external_ids.get(group.id)
        if xmlid:
            group_xmlids.append(xmlid)
    return sorted(group_xmlids)


def _access_context_for_user(user, company, ctx):
    ctx = ctx or {}
    allowed_company_ids = list(user.company_ids.ids)
    active_company_id = company.id if company else user.company_id.id
    group_xmlids = _group_xmlids_for_user(user)
    return {
        "uid": user.id,
        "user_id": user.id,
        "company_id": active_company_id,
        "active_company_id": active_company_id,
        "company_ids": allowed_company_ids,
        "allowed_company_ids": allowed_company_ids,
        "groups": group_xmlids,
        "groups_hash": _hash_groups(group_xmlids),
        "lang": ctx.get("lang"),
        "tz": ctx.get("tz"),
    }


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


def _get_request_id(client_context):
    if isinstance(client_context, dict):
        rid = client_context.get("request_id")
        if rid:
            return str(rid)
    return f"req_{uuid.uuid4().hex[:12]}"


def _company_currency_meta():
    company = request.env.company
    currency = company.currency_id if company else None
    return {
        "currency_symbol": currency.symbol if currency else None,
        "currency_name": currency.name if currency else None,
    }


MODEL_CONTEXT_SUGGESTIONS = {
    "purchase.order": [
        {"label": "Ver pickings", "prompt": "muéstrame los pickings asociados"},
        {"label": "Recepciones pendientes", "prompt": "muéstrame las recepciones pendientes"},
        {"label": "Recepciones canceladas", "prompt": "muéstrame las recepciones canceladas"},
        {"label": "Facturas del proveedor", "prompt": "muéstrame las facturas relacionadas"},
        {"label": "Productos pendientes", "prompt": "muéstrame sus productos"},
    ],
    "sale.order": [
        {"label": "Facturas relacionadas", "prompt": "muéstrame las facturas relacionadas"},
        {"label": "Pagos pendientes", "prompt": "muéstrame los pagos pendientes"},
        {"label": "Productos vendidos", "prompt": "muéstrame sus productos"},
        {"label": "Margen estimado", "prompt": "cuál es el margen estimado de esta venta"},
    ],
    "account.move": [
        {"label": "Ver vencidas", "prompt": "muéstrame las facturas vencidas"},
        {"label": "Filtrar por cliente", "prompt": "filtra por cliente"},
        {"label": "Estado de pago", "prompt": "cuál es el estado de pago"},
        {"label": "Exportar", "prompt": "exporta este resultado"},
    ],
    "stock.picking": [
        {"label": "Movimientos", "prompt": "muéstrame los movimientos de este picking"},
        {"label": "Pendientes", "prompt": "qué pickings están pendientes"},
        {"label": "Cancelados", "prompt": "qué pickings están cancelados"},
    ],
}


def _selection_label(record, field_name, value):
    if not value:
        return value
    field = record._fields.get(field_name)
    selection = field.selection if field else None
    if not selection:
        return value
    try:
        options = selection(record.env) if callable(selection) else selection
        return dict(options).get(value, value)
    except Exception:
        return value


def _context_summary_for_record(active_model, active_id):
    if not active_model or not active_id:
        return {
            "summary_text": "Sin contexto activo",
            "suggestions": [],
        }

    try:
        active_id = int(active_id)
    except Exception:
        return {
            "summary_text": "Sin contexto activo",
            "suggestions": [],
        }

    try:
        Model = request.env[active_model]
    except Exception:
        return {
            "summary_text": f"Contexto activo: {active_model} #{active_id}",
            "suggestions": MODEL_CONTEXT_SUGGESTIONS.get(active_model, []),
        }

    record = Model.browse(active_id).exists()
    if not record:
        return {
            "summary_text": f"Contexto activo: {active_model} #{active_id}",
            "suggestions": MODEL_CONTEXT_SUGGESTIONS.get(active_model, []),
        }

    if active_model == "purchase.order":
        supplier = record.partner_id.name if record.partner_id else "-"
        state_label = _selection_label(record, "state", record.state) or "-"
        pickings_count = len(record.picking_ids) if hasattr(record, "picking_ids") else 0
        name = record.name or f"#{active_id}"
        return {
            "summary_text": f"Compra {name} · Proveedor: {supplier} · Estado: {state_label} · Pickings: {pickings_count}",
            "suggestions": MODEL_CONTEXT_SUGGESTIONS.get(active_model, []),
        }

    if active_model == "sale.order":
        customer = record.partner_id.name if record.partner_id else "-"
        state_label = _selection_label(record, "state", record.state) or "-"
        name = record.name or f"#{active_id}"
        return {
            "summary_text": f"Venta {name} · Cliente: {customer} · Estado: {state_label}",
            "suggestions": MODEL_CONTEXT_SUGGESTIONS.get(active_model, []),
        }

    if active_model == "account.move":
        partner = record.partner_id.name if record.partner_id else "-"
        state_label = _selection_label(record, "state", record.state) or "-"
        payment_label = _selection_label(record, "payment_state", record.payment_state) or "-"
        name = record.name or f"#{active_id}"
        return {
            "summary_text": f"Factura {name} · Contacto: {partner} · Estado: {state_label} · Pago: {payment_label}",
            "suggestions": MODEL_CONTEXT_SUGGESTIONS.get(active_model, []),
        }

    if active_model == "stock.picking":
        partner = record.partner_id.name if record.partner_id else "-"
        state_label = _selection_label(record, "state", record.state) or "-"
        name = record.name or f"#{active_id}"
        return {
            "summary_text": f"Picking {name} · Contacto: {partner} · Estado: {state_label}",
            "suggestions": MODEL_CONTEXT_SUGGESTIONS.get(active_model, []),
        }

    return {
        "summary_text": f"Contexto activo: {active_model} #{active_id}",
        "suggestions": MODEL_CONTEXT_SUGGESTIONS.get(active_model, []),
    }


def _score_action_for_open_type(view_mode, open_type):
    vm = str(view_mode or "")
    score = 0
    if open_type == "form":
        if "form" in vm:
            score += 10
        if "tree" in vm or "list" in vm:
            score += 1
    else:
        if "tree" in vm or "list" in vm:
            score += 10
        if "kanban" in vm:
            score += 2
        if "form" in vm:
            score += 1
    return score


def _resolve_navigation_for_model(model_name, open_type="list"):
    if not model_name:
        return {}

    ActWindow = request.env["ir.actions.act_window"].sudo()
    actions = ActWindow.search([("res_model", "=", model_name)])
    if not actions:
        return {}

    best_action = None
    best_score = -1
    for action in actions:
        score = _score_action_for_open_type(action.view_mode, open_type)
        if score > best_score:
            best_score = score
            best_action = action

    if not best_action:
        best_action = actions[0]

    menu = request.env["ir.ui.menu"].sudo().search(
        [("action", "=", f"ir.actions.act_window,{best_action.id}")],
        limit=1,
    )

    return {
        "action_id": best_action.id,
        "menu_id": menu.id if menu else None,
    }


def _normalize_ai_response_payload(result, answer, request_id, currency_meta):
    result = result if isinstance(result, dict) else {}
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    metadata = dict(result.get("metadata") or {})

    tools_used = result.get("tools_used") or metrics.get("tools_used") or metadata.get("tools_used") or []
    route = result.get("route_selected") or result.get("route") or result.get("answer_mode")
    latency_ms = result.get("latency_ms", metadata.get("latency_ms"))
    tokens_used = result.get("tokens_used", metadata.get("tokens_used"))
    active_model = result.get("active_model") or metrics.get("active_model")
    active_id = result.get("active_id") or metrics.get("active_id")

    context_scope = dict(metadata.get("context_scope") or {})
    if active_model:
        context_scope["active_model"] = active_model
    if active_id:
        context_scope["active_id"] = active_id

    metadata.update({
        "route_selected": route,
        "intent_detected": result.get("intent_detected") or metrics.get("intent_detected"),
        "domain_detected": result.get("domain_detected") or metrics.get("domain_detected"),
        "tools_used": tools_used,
        "sources": result.get("sources") or metadata.get("sources") or [],
        "odoo_evidence": result.get("odoo_evidence") or metadata.get("odoo_evidence") or [],
        "latency_ms": latency_ms,
        "tokens_used": tokens_used,
        "context_scope": context_scope,
    })
    if currency_meta.get("currency_symbol"):
        metadata["currency_symbol"] = currency_meta.get("currency_symbol")
    if currency_meta.get("currency_name"):
        metadata["currency_name"] = currency_meta.get("currency_name")

    return {
        "answer": answer,
        "answer_mode": result.get("answer_mode") or route,
        "answer_type": result.get("answer_type") or ("error" if result.get("error") else None),
        "needs_clarification": result.get("needs_clarification", False),
        "clarification_options": result.get("clarification_options") or [],
        "actions": result.get("actions") or [],
        "metadata": metadata,
        "error_code": result.get("error_code") or result.get("error_type"),
        "request_id": result.get("request_id") or result.get("trace_id") or request_id,
        "ui": result.get("ui"),
        "sources": result.get("sources") or [],
        "odoo_evidence": result.get("odoo_evidence") or [],
        "metrics": metrics,
    }


class AIChatController(http.Controller):

    @http.route("/ai_assistant/ask", type="json", auth="user")
    def ask(self, question, context=None):
        ai_url = AI_SERVICE_URL
        request_id = _get_request_id(context or {})
        _logger.info(
            "AI_ASK_JSON_START %s",
            json.dumps({"request_id": request_id, "question": question}, ensure_ascii=False),
        )
        user = request.env.user
        company = request.env.company
        ctx = request.context or {}
        access_context = _access_context_for_user(user, company, ctx)
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

        currency_meta = _company_currency_meta()
        payload = {
            "question": question,
            "session_id": session_key or request_id,
            "history": history_payload,
            "context": {
                "user": {"id": user.id, "name": user.name},
                "security": access_context,
                "access_context": access_context,
                "company": {
                    "id": company.id,
                    "name": company.name,
                    "currency_symbol": currency_meta.get("currency_symbol"),
                    "currency_name": currency_meta.get("currency_name"),
                },
                "lang": ctx.get("lang"),
                "tz": ctx.get("tz"),
                "client": context or {},
                "memory": memory,
                "history_limit": history_limit,
                "use_server_history": use_server_history,
                "history_server": history_payload,
                "request_id": request_id,
            },
        }
        try:
            response = requests.post(ai_url, json=payload, headers=_ai_service_headers(), timeout=20)
        except RequestException:
            _logger.exception("AI ask (json) request failed")
            return {
                "answer": "No pude conectar con el servicio de IA. Intenta nuevamente.",
                "answer_mode": "fallback_explanatory",
                "answer_type": "error",
                "needs_clarification": False,
                "clarification_options": [],
                "actions": [],
                "metadata": {"latency_ms": None, "tools_used": [], "context_scope": {}},
                "error_code": "ERR_TOOL_TIMEOUT",
                "request_id": request_id,
                "ui": None,
            }
        _logger.info("AI_ASK_JSON_HTTP request_id=%s status=%s", request_id, response.status_code)

        answer = ""
        memory_response = None
        result = {}
        try:
            result = response.json()
            answer = result.get("answer", "")
            memory_response = result.get("memory")
        except Exception:
            _logger.exception("AI ask (json) response is not JSON")
            answer = "Ocurrió un error al procesar la respuesta del servicio de IA."
            result = {}

        _save_session_memory(user.id, session_key, memory_response)

        request.env["ai.chat"].sudo().create({
            "user_id": request.env.user.id,
            "session_key": session_key,
            "question": question,
            "answer": answer
        })

        response_payload = _normalize_ai_response_payload(result, answer, request_id, currency_meta)
        _logger.info(
            "AI_ASK_JSON_END %s",
            json.dumps(
                {
                    "request_id": response_payload.get("request_id"),
                    "answer_mode": response_payload.get("answer_mode"),
                    "error_code": response_payload.get("error_code"),
                },
                ensure_ascii=False,
            ),
        )
        return response_payload

    @http.route("/ai_assistant/ask_http", type="http", auth="user", csrf=False, methods=["POST"])
    def ask_http(self, **kwargs):
        data = request.httprequest.get_json(silent=True) or {}
        question = data.get("question") or ""
        client_context = data.get("context") or {}
        request_id = _get_request_id(client_context)
        client_context["request_id"] = request_id
        if not question:
            return request.make_json_response({"answer": ""})

        ai_url = AI_SERVICE_URL
        _logger.info(
            "AI_ASK_HTTP_START %s",
            json.dumps({"request_id": request_id, "question": question}, ensure_ascii=False),
        )
        user = request.env.user
        company = request.env.company
        ctx = request.context or {}
        access_context = _access_context_for_user(user, company, ctx)
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
        currency_meta = _company_currency_meta()
        payload = {
            "question": question,
            "session_id": session_key or request_id,
            "history": history_payload,
            "context": {
                "user": {"id": user.id, "name": user.name},
                "security": access_context,
                "access_context": access_context,
                "company": {
                    "id": company.id,
                    "name": company.name,
                    "currency_symbol": currency_meta.get("currency_symbol"),
                    "currency_name": currency_meta.get("currency_name"),
                },
                "lang": ctx.get("lang"),
                "tz": ctx.get("tz"),
                "client": client_context,
                "memory": memory,
                "history_limit": history_limit,
                "use_server_history": use_server_history,
                "history_server": history_payload,
                "request_id": request_id,
            },
        }
        try:
            response = requests.post(ai_url, json=payload, headers=_ai_service_headers(), timeout=60)
        except RequestException:
            _logger.exception("AI ask_http request failed")
            return request.make_json_response(
                {
                    "answer": "No pude conectar con el servicio de IA. Intenta nuevamente.",
                    "answer_mode": "fallback_explanatory",
                    "answer_type": "error",
                    "needs_clarification": False,
                    "clarification_options": [],
                    "actions": [],
                    "metadata": {"latency_ms": None, "tools_used": [], "context_scope": {}},
                    "error_code": "ERR_TOOL_TIMEOUT",
                    "request_id": request_id,
                    "ui": None,
                }
            )
        _logger.info("AI_ASK_HTTP_REQUEST request_id=%s status=%s", request_id, response.status_code)

        answer = ""
        memory_response = None
        result = {}
        try:
            result = response.json()
            answer = result.get("answer", "")
            memory_response = result.get("memory")
        except Exception:
            _logger.exception("AI ask_http response is not JSON")
            answer = "Ocurrió un error al procesar la respuesta del servicio de IA."
            result = {}

        _save_session_memory(user.id, session_key, memory_response)

        request.env["ai.chat"].sudo().create({
            "user_id": request.env.user.id,
            "session_key": session_key,
            "question": question,
            "answer": answer
        })

        response_payload = _normalize_ai_response_payload(result, answer, request_id, currency_meta)
        _logger.info(
            "AI_ASK_HTTP_END %s",
            json.dumps(
                {
                    "request_id": response_payload.get("request_id"),
                    "answer_mode": response_payload.get("answer_mode"),
                    "error_code": response_payload.get("error_code"),
                },
                ensure_ascii=False,
            ),
        )
        return request.make_json_response(response_payload)

    @http.route("/ai_assistant/context_summary", type="http", auth="user", csrf=False, methods=["POST"])
    def context_summary(self, **kwargs):
        data = request.httprequest.get_json(silent=True) or {}
        context = data.get("context") if isinstance(data, dict) else {}
        context = context if isinstance(context, dict) else {}

        active_model = context.get("active_model")
        active_id = context.get("active_id")

        payload = _context_summary_for_record(active_model, active_id)
        payload["active_model"] = active_model
        payload["active_id"] = active_id
        return request.make_json_response(payload)

    @http.route("/ai_assistant/resolve_navigation", type="http", auth="user", csrf=False, methods=["POST"])
    def resolve_navigation(self, **kwargs):
        data = request.httprequest.get_json(silent=True) or {}
        model = data.get("model")
        action_type = data.get("type")
        open_type = "form" if action_type == "open_record" else "list"

        if not model:
            return request.make_json_response({"ok": False, "error": "missing model"})

        try:
            resolved = _resolve_navigation_for_model(str(model), open_type=open_type)
            if not resolved:
                return request.make_json_response({"ok": False, "error": "navigation not found"})
            return request.make_json_response({"ok": True, **resolved})
        except Exception as e:
            _logger.exception("resolve_navigation failed")
            return request.make_json_response({"ok": False, "error": str(e)})


class AIController(http.Controller):

    @http.route("/ai/get_data", type="http", auth="public", csrf=False, methods=["POST"])
    def ai_query(self, **kwargs):
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
        audit_context = None

        try:
            model = _validate_model_name(model)
            if operation not in AI_ALLOWED_OPERATIONS:
                return _error_response("ERR_OPERATION_NOT_ALLOWED", "Operación no permitida.", status=403)

            domain = _validate_domain(domain, model_name=model)
            fields = _validate_fields(fields)
            ids = _validate_ids(ids)
            groupby = _validate_groupby(groupby)
            orderby = _validate_orderby(orderby)

            if operation in ("search", "search_read", "read_group"):
                limit = _clamp_limit(params.get("limit"), default=min(AI_DEFAULT_LIMIT, AI_MAX_LIMIT))
            else:
                limit = None

            Model, audit_context = _scoped_model(model, params)

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
                records = Model.browse(ids).exists()
                records.check_access("read")
                result = records.read(fields)
            elif operation == "read_group":
                if not fields:
                    return _error_response("ERR_INVALID_QUERY", "La operación 'read_group' requiere campos.")
                result = Model.read_group(domain, fields, groupby, orderby=orderby, limit=limit)
            else:
                return _error_response("ERR_OPERATION_NOT_ALLOWED", "Operación no permitida.", status=403)

            _log_ai_tool_audit("ok", audit_context, model, operation, domain=domain, fields=fields, result=result)
            return request.make_json_response(result)
        except (PermissionError, AccessError) as e:
            _logger.warning("AI query blocked: %s", e)
            _log_ai_tool_audit("blocked", audit_context, model, operation, domain=domain, fields=fields, error_code=str(e))
            return _error_response("ERR_PERMISSION_DENIED", "Consulta bloqueada por política de seguridad.", status=403, details=e)
        except ValueError as e:
            _logger.warning("AI query validation error: %s", e)
            _log_ai_tool_audit("invalid", audit_context, model, operation, domain=domain, fields=fields, error_code=str(e))
            return _error_response("ERR_INVALID_QUERY", "Parámetros de consulta inválidos.", status=400, details=e)
        except Exception as e:
            _logger.exception("AI query error")
            _log_ai_tool_audit("error", audit_context, model, operation, domain=domain, fields=fields, error_code=type(e).__name__)
            return _error_response("ERR_QUERY_EXECUTION", "No se pudo ejecutar la consulta.", status=500, details=e)

    @http.route("/ai/schema", type="http", auth="public", csrf=False, methods=["GET", "POST"])
    def ai_schema(self, **kwargs):
        auth_error = _require_service_token()
        if auth_error:
            return auth_error

        payload = request.httprequest.get_json(silent=True) or {}
        params = payload.get("params", payload) if isinstance(payload, dict) else {}
        force = bool(params.get("force")) if isinstance(params, dict) else False
        models_filter = params.get("models") if isinstance(params, dict) else None
        audit_context = None

        if models_filter is None:
            models_filter = sorted(AI_ALLOWED_MODELS)
        elif not isinstance(models_filter, list):
            return _error_response("ERR_INVALID_PAYLOAD", "El parámetro 'models' debe ser una lista.")

        clean_models = []
        for model_name in models_filter:
            try:
                validated = _validate_model_name(model_name)
            except PermissionError:
                return _error_response("ERR_MODEL_NOT_ALLOWED", f"Modelo no permitido: {model_name}", status=403)
            except ValueError:
                return _error_response("ERR_INVALID_PAYLOAD", f"Modelo inválido: {model_name}")
            clean_models.append(validated)

        clean_models = sorted(set(clean_models))
        if not clean_models:
            return _error_response("ERR_INVALID_PAYLOAD", "Debes solicitar al menos un modelo permitido.")
        if len(clean_models) > AI_MAX_SCHEMA_MODELS:
            return _error_response("ERR_TOO_BROAD_QUERY", "Demasiados modelos solicitados.")

        try:
            user, scoped_context, audit_context = _resolve_ai_user_scope(params)
            accessible_models = []
            for model_name in clean_models:
                Model = request.env[model_name].with_user(user.id).with_context(**scoped_context)
                if Model.browse().has_access("read"):
                    accessible_models.append(model_name)

            if not accessible_models:
                raise PermissionError("no_accessible_models")

            schema = request.env["ai.schema.cache"].sudo().get_schema(
                force=force,
                models_filter=accessible_models,
            )
            _log_ai_tool_audit("ok", audit_context, "schema", "schema", fields=accessible_models, result=schema)
            return request.make_json_response(_sanitize_schema_payload(schema))
        except (PermissionError, AccessError) as e:
            _logger.warning("AI schema blocked: %s", e)
            _log_ai_tool_audit("blocked", audit_context, "schema", "schema", fields=clean_models, error_code=str(e))
            return _error_response("ERR_PERMISSION_DENIED", "Consulta bloqueada por política de seguridad.", status=403, details=e)
        except Exception as e:
            _logger.exception("AI schema error")
            _log_ai_tool_audit("error", audit_context, "schema", "schema", fields=clean_models, error_code=type(e).__name__)
            return _error_response("ERR_SCHEMA_EXECUTION", "No se pudo obtener schema.", status=500, details=e)
