from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager

logger = logging.getLogger("odoo_ai_service")


def log_agent_event(event: str, **payload):
    logger.info(
        "AGENT_EVENT %s",
        json.dumps(
            {"event": event, **payload},
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
