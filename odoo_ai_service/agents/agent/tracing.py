from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager

logger = logging.getLogger("odoo_ai_service")

SENSITIVE_KEYS = {"password", "token", "secret", "api_key", "access_token", "client_secret"}


def _compact_context(value):
    if not isinstance(value, dict):
        return {}
    access_context = value.get("access_context") if isinstance(value.get("access_context"), dict) else {}
    client = value.get("client") if isinstance(value.get("client"), dict) else {}
    return {
        "request_id": value.get("request_id") or client.get("request_id") or access_context.get("request_id"),
        "session_id": value.get("session_id") or client.get("chat_session_key") or access_context.get("session_id"),
        "db_name": value.get("db_name") or access_context.get("db_name"),
        "user_id": access_context.get("user_id") or access_context.get("uid"),
        "active_model": client.get("active_model"),
        "active_id": client.get("active_id"),
    }


def _sanitize(value, key: str | None = None):
    normalized_key = str(key or "").lower()
    if normalized_key == "context":
        return _compact_context(value)
    if normalized_key in SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {item_key: _sanitize(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value[:20]]
    return value


def log_agent_event(event: str, **payload):
    logger.info(
        "AGENT_EVENT %s",
        json.dumps(
            _sanitize({"event": event, **payload}),
            ensure_ascii=False,
            default=str,
        ),
    )


@contextmanager
def trace_step(event: str, **payload):
    start = time.perf_counter()
    log_agent_event(f"{event}_start", **payload)
    try:
        yield
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        log_agent_event(
            f"{event}_error",
            elapsed_ms=elapsed_ms,
            error_type=type(exc).__name__,
            **payload,
        )
        raise
    else:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        log_agent_event(f"{event}_end", elapsed_ms=elapsed_ms, **payload)
