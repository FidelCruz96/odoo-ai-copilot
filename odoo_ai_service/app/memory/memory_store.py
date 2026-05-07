from __future__ import annotations

from app.memory.schemas import ActiveEntity, ConversationMemory


class InMemoryStore:
    def __init__(self):
        self._sessions: dict[str, ConversationMemory] = {}

    def get(self, session_id: str) -> ConversationMemory | None:
        return self._sessions.get(session_id)

    def set(self, session_id: str, memory: ConversationMemory) -> None:
        self._sessions[session_id] = memory


_STORE = InMemoryStore()


def get_store() -> InMemoryStore:
    return _STORE


def load_memory(session_id: str | None, context: dict | None) -> ConversationMemory | None:
    raw_memory = context.get("memory") if isinstance(context, dict) else None
    if isinstance(raw_memory, dict):
        if not raw_memory and session_id:
            return get_store().get(session_id)
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
        return ConversationMemory(
            session_id=session_id or "anonymous",
            active_entity=active_entity,
            last_route=raw_memory.get("last_route"),
            last_intent=raw_memory.get("last_intent"),
            last_fields=raw_memory.get("last_fields") or {},
            last_tools_used=raw_memory.get("last_tools_used") or [],
            last_sources=raw_memory.get("last_sources") or [],
        )

    if session_id:
        return get_store().get(session_id)
    return None


def persist_memory(memory: ConversationMemory) -> None:
    get_store().set(memory.session_id, memory)
