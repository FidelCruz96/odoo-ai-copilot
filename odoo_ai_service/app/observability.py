from __future__ import annotations

import json
import logging
from typing import Any


SENSITIVE_KEYS = {
    "authorization",
    "password",
    "token",
    "api_key",
    "access_token",
    "secret",
    "ai_service_api_key",
}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if str(key).lower() in SENSITIVE_KEYS else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "...[truncated]"
    return value


def emit_event(logger: logging.Logger, event: str, **payload: Any) -> None:
    logger.info(
        "OBS_EVENT %s",
        json.dumps(
            {"event": event, **_redact(payload)},
            ensure_ascii=False,
            default=str,
        ),
    )
