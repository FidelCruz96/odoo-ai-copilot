from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any, Protocol

from app.memory.schemas import ActiveEntity, ConversationMemory
from app.observability import emit_event

logger = logging.getLogger("odoo_ai_service")

DEFAULT_DB_NAME = "default"
ANONYMOUS_USER_ID = 0
SENSITIVE_KEYS = {"password", "password_crypt", "token", "secret", "api_key", "access_token", "client_secret"}


class ConversationMemoryStore(Protocol):
    def get(self, *, user_id: int, session_id: str, db_name: str) -> ConversationMemory | None:
        ...

    def save(self, *, user_id: int, session_id: str, db_name: str, memory: ConversationMemory) -> None:
        ...

    def clear(self, *, user_id: int, session_id: str, db_name: str) -> None:
        ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _memory_ttl_seconds() -> int:
    raw = os.getenv("MEMORY_TTL_SECONDS", "86400")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 86400
    return max(value, 60)


def _coerce_user_id(value: Any) -> int:
    try:
        user_id = int(value)
    except (TypeError, ValueError):
        return ANONYMOUS_USER_ID
    return user_id if user_id > 0 else ANONYMOUS_USER_ID


def _coerce_db_name(value: Any) -> str:
    db_name = str(value or "").strip()
    return db_name or DEFAULT_DB_NAME


def _coerce_session_id(value: Any) -> str:
    session_id = str(value or "").strip()
    return session_id or "anonymous"


def _normalize_scope(*, user_id: Any = None, session_id: Any = None, db_name: Any = None) -> tuple[int, str, str]:
    return _coerce_user_id(user_id), _coerce_session_id(session_id), _coerce_db_name(db_name)


def _extract_scope_from_context(session_id: str | None, context: dict | None) -> tuple[int, str, str]:
    context = context if isinstance(context, dict) else {}
    access_context = context.get("access_context") or context.get("security") or {}
    user_context = context.get("user") or {}

    user_id = None
    if isinstance(access_context, dict):
        user_id = access_context.get("uid") or access_context.get("user_id")
    if user_id is None and isinstance(user_context, dict):
        user_id = user_context.get("id")

    db_name = context.get("db_name") or context.get("database") or context.get("db")
    if db_name is None and isinstance(access_context, dict):
        db_name = access_context.get("db_name") or access_context.get("database") or access_context.get("db")

    return _normalize_scope(user_id=user_id, session_id=session_id, db_name=db_name)


def memory_scope_from_context(session_id: str | None, context: dict | None) -> tuple[int, str, str]:
    return _extract_scope_from_context(session_id, context)


def _is_expired(memory: ConversationMemory | None) -> bool:
    if memory is None or not memory.expires_at:
        return False
    expires_at = memory.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= _now()


def _safe_mapping(payload: dict[str, Any] | None) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in (payload or {}).items():
        if str(key).lower() in SENSITIVE_KEYS:
            continue
        clean[key] = value
    return clean


class InMemoryStore:
    def __init__(self):
        self._sessions: dict[tuple[str, int, str], ConversationMemory] = {}

    def get(self, *, user_id: int = ANONYMOUS_USER_ID, session_id: str, db_name: str = DEFAULT_DB_NAME) -> ConversationMemory | None:
        scope = _normalize_scope(user_id=user_id, session_id=session_id, db_name=db_name)
        memory = self._sessions.get((scope[2], scope[0], scope[1]))
        if _is_expired(memory):
            self._sessions.pop((scope[2], scope[0], scope[1]), None)
            return None
        return memory

    def set(self, session_id: str, memory: ConversationMemory) -> None:
        user_id, scoped_session_id, db_name = _normalize_scope(
            user_id=memory.user_id,
            session_id=session_id or memory.session_id,
            db_name=memory.db_name,
        )
        self.save(user_id=user_id, session_id=scoped_session_id, db_name=db_name, memory=memory)

    def save(self, *, user_id: int, session_id: str, db_name: str, memory: ConversationMemory) -> None:
        user_id, session_id, db_name = _normalize_scope(user_id=user_id, session_id=session_id, db_name=db_name)
        now = _now()
        memory.user_id = user_id
        memory.session_id = session_id
        memory.db_name = db_name
        memory.created_at = memory.created_at or now
        memory.updated_at = now
        memory.expires_at = now + timedelta(seconds=_memory_ttl_seconds())
        memory.last_fields = _safe_mapping(memory.last_fields)
        memory.metadata = _safe_mapping(memory.metadata)
        self._sessions[(db_name, user_id, session_id)] = memory

    def clear(self, *, user_id: int, session_id: str, db_name: str) -> None:
        user_id, session_id, db_name = _normalize_scope(user_id=user_id, session_id=session_id, db_name=db_name)
        self._sessions.pop((db_name, user_id, session_id), None)


class PostgresMemoryStore:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self._schema_ready = False

    def _connect(self):
        import psycopg2

        return psycopg2.connect(self.database_url)

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        ddl = """
        CREATE TABLE IF NOT EXISTS ai_conversation_memory (
            id BIGSERIAL PRIMARY KEY,
            db_name TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            active_model TEXT,
            active_id INTEGER,
            active_name TEXT,
            active_domain TEXT,
            active_intent TEXT,
            last_question TEXT,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ NOT NULL,
            UNIQUE (db_name, user_id, session_id)
        );
        CREATE INDEX IF NOT EXISTS ai_conversation_memory_expiry_idx
            ON ai_conversation_memory (expires_at);
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
        self._schema_ready = True

    def get(self, *, user_id: int, session_id: str, db_name: str) -> ConversationMemory | None:
        from psycopg2.extras import RealDictCursor

        user_id, session_id, db_name = _normalize_scope(user_id=user_id, session_id=session_id, db_name=db_name)
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT payload
                    FROM ai_conversation_memory
                    WHERE db_name = %s
                      AND user_id = %s
                      AND session_id = %s
                      AND expires_at > now()
                    """,
                    (db_name, user_id, session_id),
                )
                row = cur.fetchone()
        if not row:
            return None
        payload = dict(row["payload"] or {})
        return _memory_from_context_dict(session_id, payload, user_id=user_id, db_name=db_name)

    def save(self, *, user_id: int, session_id: str, db_name: str, memory: ConversationMemory) -> None:
        from psycopg2.extras import Json

        user_id, session_id, db_name = _normalize_scope(user_id=user_id, session_id=session_id, db_name=db_name)
        self._ensure_schema()
        now = _now()
        memory.user_id = user_id
        memory.session_id = session_id
        memory.db_name = db_name
        memory.created_at = memory.created_at or now
        memory.updated_at = now
        memory.expires_at = now + timedelta(seconds=_memory_ttl_seconds())
        memory.last_fields = _safe_mapping(memory.last_fields)
        memory.metadata = _safe_mapping(memory.metadata)
        payload = memory.to_context_dict()
        active = payload.get("active_entity") if isinstance(payload.get("active_entity"), dict) else {}
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ai_conversation_memory (
                        db_name, user_id, session_id, active_model, active_id, active_name,
                        active_domain, active_intent, last_question, payload, metadata, created_at, updated_at, expires_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (db_name, user_id, session_id)
                    DO UPDATE SET
                        active_model = EXCLUDED.active_model,
                        active_id = EXCLUDED.active_id,
                        active_name = EXCLUDED.active_name,
                        active_domain = EXCLUDED.active_domain,
                        active_intent = EXCLUDED.active_intent,
                        last_question = EXCLUDED.last_question,
                        payload = EXCLUDED.payload,
                        metadata = EXCLUDED.metadata,
                        updated_at = EXCLUDED.updated_at,
                        expires_at = EXCLUDED.expires_at
                    """,
                    (
                        db_name,
                        user_id,
                        session_id,
                        active.get("model"),
                        active.get("id"),
                        active.get("name") or active.get("display_name"),
                        memory.active_domain,
                        memory.last_intent,
                        memory.last_question,
                        Json(payload),
                        Json(_safe_mapping(memory.metadata)),
                        memory.created_at,
                        memory.updated_at,
                        memory.expires_at,
                    ),
                )

    def clear(self, *, user_id: int, session_id: str, db_name: str) -> None:
        user_id, session_id, db_name = _normalize_scope(user_id=user_id, session_id=session_id, db_name=db_name)
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM ai_conversation_memory WHERE db_name = %s AND user_id = %s AND session_id = %s",
                    (db_name, user_id, session_id),
                )


_STORE: ConversationMemoryStore | None = None


def _build_store() -> ConversationMemoryStore:
    backend = os.getenv("MEMORY_STORE", "in_memory").strip().lower()
    if backend == "postgres":
        database_url = os.getenv("MEMORY_DATABASE_URL") or os.getenv("DATABASE_URL")
        if not database_url:
            logger.warning("MEMORY_STORE=postgres configured without MEMORY_DATABASE_URL; falling back to in_memory")
            return InMemoryStore()
        return PostgresMemoryStore(database_url)
    return InMemoryStore()


def get_store() -> ConversationMemoryStore:
    global _STORE
    if _STORE is None:
        _STORE = _build_store()
    return _STORE


def reset_store_for_tests(store: ConversationMemoryStore | None = None) -> None:
    global _STORE
    _STORE = store or InMemoryStore()


def _memory_from_context_dict(
    session_id: str | None,
    raw_memory: dict[str, Any],
    *,
    user_id: int | None = None,
    db_name: str | None = None,
) -> ConversationMemory:
    active_raw = raw_memory.get("active_entity") or raw_memory.get("last_entity")
    active_entity = None
    if isinstance(active_raw, dict) and active_raw.get("model") and active_raw.get("id"):
        active_entity = ActiveEntity(
            type=str(active_raw.get("type") or active_raw.get("model")),
            model=str(active_raw.get("model")),
            id=int(active_raw.get("id")),
            name=active_raw.get("name") or active_raw.get("display_name"),
            confidence=float(active_raw.get("confidence") or 1.0),
        )
    scoped_user_id, scoped_session_id, scoped_db_name = _normalize_scope(
        user_id=raw_memory.get("user_id") or user_id,
        session_id=session_id,
        db_name=raw_memory.get("db_name") or db_name,
    )
    return ConversationMemory(
        session_id=scoped_session_id,
        user_id=scoped_user_id,
        db_name=scoped_db_name,
        active_entity=active_entity,
        active_domain=raw_memory.get("active_domain"),
        last_route=raw_memory.get("last_route"),
        last_intent=raw_memory.get("last_intent"),
        last_question=raw_memory.get("last_question"),
        last_fields=_safe_mapping(raw_memory.get("last_fields") or {}),
        last_tools_used=raw_memory.get("last_tools_used") or [],
        last_sources=raw_memory.get("last_sources") or [],
        metadata=_safe_mapping(raw_memory.get("metadata") or {}),
    )


def load_memory(session_id: str | None, context: dict | None) -> ConversationMemory | None:
    user_id, scoped_session_id, db_name = _extract_scope_from_context(session_id, context)
    trace_id = context.get("request_id") if isinstance(context, dict) else None
    started_at = perf_counter()
    raw_memory = context.get("memory") if isinstance(context, dict) else None
    if isinstance(raw_memory, dict):
        if raw_memory:
            memory = _memory_from_context_dict(scoped_session_id, raw_memory, user_id=user_id, db_name=db_name)
            emit_event(
                logger,
                "MEMORY_LOAD",
                trace_id=trace_id,
                store="request",
                db_name=db_name,
                user_id=user_id,
                session_id=scoped_session_id,
                hit=bool(memory.active_entity),
                latency_ms=round((perf_counter() - started_at) * 1000, 2),
            )
            return memory
        try:
            memory = get_store().get(user_id=user_id, session_id=scoped_session_id, db_name=db_name)
            emit_event(
                logger,
                "MEMORY_LOAD",
                trace_id=trace_id,
                store=os.getenv("MEMORY_STORE", "in_memory"),
                db_name=db_name,
                user_id=user_id,
                session_id=scoped_session_id,
                hit=bool(memory and memory.active_entity),
                latency_ms=round((perf_counter() - started_at) * 1000, 2),
            )
            return memory
        except Exception:
            logger.exception("conversation_memory_load_failed")
            emit_event(
                logger,
                "MEMORY_LOAD",
                trace_id=trace_id,
                store=os.getenv("MEMORY_STORE", "in_memory"),
                db_name=db_name,
                user_id=user_id,
                session_id=scoped_session_id,
                hit=False,
                success=False,
                error_type="memory_load_failed",
                latency_ms=round((perf_counter() - started_at) * 1000, 2),
            )
            return None

    if session_id:
        try:
            memory = get_store().get(user_id=user_id, session_id=scoped_session_id, db_name=db_name)
            emit_event(
                logger,
                "MEMORY_LOAD",
                trace_id=trace_id,
                store=os.getenv("MEMORY_STORE", "in_memory"),
                db_name=db_name,
                user_id=user_id,
                session_id=scoped_session_id,
                hit=bool(memory and memory.active_entity),
                latency_ms=round((perf_counter() - started_at) * 1000, 2),
            )
            return memory
        except Exception:
            logger.exception("conversation_memory_load_failed")
            emit_event(
                logger,
                "MEMORY_LOAD",
                trace_id=trace_id,
                store=os.getenv("MEMORY_STORE", "in_memory"),
                db_name=db_name,
                user_id=user_id,
                session_id=scoped_session_id,
                hit=False,
                success=False,
                error_type="memory_load_failed",
                latency_ms=round((perf_counter() - started_at) * 1000, 2),
            )
    return None


def persist_memory(memory: ConversationMemory, *, user_id: int | None = None, db_name: str | None = None) -> None:
    scoped_user_id, scoped_session_id, scoped_db_name = _normalize_scope(
        user_id=user_id if user_id is not None else memory.user_id,
        session_id=memory.session_id,
        db_name=db_name if db_name is not None else memory.db_name,
    )
    started_at = perf_counter()
    try:
        get_store().save(user_id=scoped_user_id, session_id=scoped_session_id, db_name=scoped_db_name, memory=memory)
        emit_event(
            logger,
            "MEMORY_SAVE",
            trace_id=(memory.metadata or {}).get("trace_id"),
            store=os.getenv("MEMORY_STORE", "in_memory"),
            db_name=scoped_db_name,
            user_id=scoped_user_id,
            session_id=scoped_session_id,
            success=True,
            latency_ms=round((perf_counter() - started_at) * 1000, 2),
        )
    except Exception:
        logger.exception("conversation_memory_persist_failed")
        emit_event(
            logger,
            "MEMORY_SAVE",
            trace_id=(memory.metadata or {}).get("trace_id"),
            store=os.getenv("MEMORY_STORE", "in_memory"),
            db_name=scoped_db_name,
            user_id=scoped_user_id,
            session_id=scoped_session_id,
            success=False,
            error_type="memory_save_failed",
            latency_ms=round((perf_counter() - started_at) * 1000, 2),
        )


def clear_memory(session_id: str, context: dict | None = None) -> None:
    user_id, scoped_session_id, db_name = _extract_scope_from_context(session_id, context)
    try:
        get_store().clear(user_id=user_id, session_id=scoped_session_id, db_name=db_name)
    except Exception:
        logger.exception("conversation_memory_clear_failed")
