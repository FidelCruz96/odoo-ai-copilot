import sys
import types
import unittest


if "pydantic" not in sys.modules:
    pydantic_stub = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

        def dict(self):
            return dict(self.__dict__)

        def model_dump(self):
            return dict(self.__dict__)

    def Field(default=None, **kwargs):
        if "default_factory" in kwargs:
            return kwargs["default_factory"]()
        return kwargs.get("default", default)

    pydantic_stub.BaseModel = BaseModel
    pydantic_stub.Field = Field
    sys.modules["pydantic"] = pydantic_stub


from datetime import datetime, timedelta, timezone

from app.memory.memory_store import InMemoryStore, get_store, load_memory, persist_memory, reset_store_for_tests
from app.memory.schemas import ActiveEntity, ConversationMemory


class TestMemoryLoading(unittest.TestCase):
    def setUp(self):
        reset_store_for_tests()
        get_store()._sessions.clear()

    def test_empty_context_memory_falls_back_to_session_store(self):
        persist_memory(
            ConversationMemory(
                session_id="sess-1",
                user_id=7,
                db_name="odoo_demo",
                active_entity=ActiveEntity(
                    type="purchase_order",
                    model="purchase.order",
                    id=113,
                    name="PO-I-10-00026",
                ),
                last_route="erp_data",
                last_intent="amount_lookup",
                last_fields={"amount_total": 122100.0},
                last_tools_used=["query_odoo_search", "query_odoo_read"],
            ),
            user_id=7,
            db_name="odoo_demo",
        )

        loaded = load_memory("sess-1", {"security": {"uid": 7, "db_name": "odoo_demo"}, "memory": {}})

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.active_entity.id, 113)
        self.assertEqual(loaded.last_route, "erp_data")

    def test_memory_is_isolated_by_user_session_and_database(self):
        store = InMemoryStore()
        memory = ConversationMemory(
            session_id="sess-1",
            active_entity=ActiveEntity(type="purchase_order", model="purchase.order", id=113, name="PO-I-10-00026"),
        )

        store.save(user_id=7, session_id="sess-1", db_name="odoo_demo", memory=memory)

        self.assertIsNotNone(store.get(user_id=7, session_id="sess-1", db_name="odoo_demo"))
        self.assertIsNone(store.get(user_id=8, session_id="sess-1", db_name="odoo_demo"))
        self.assertIsNone(store.get(user_id=7, session_id="sess-2", db_name="odoo_demo"))
        self.assertIsNone(store.get(user_id=7, session_id="sess-1", db_name="other_db"))

    def test_expired_memory_is_ignored(self):
        store = InMemoryStore()
        expired = ConversationMemory(
            session_id="sess-1",
            user_id=7,
            db_name="odoo_demo",
            active_entity=ActiveEntity(type="purchase_order", model="purchase.order", id=113),
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        store._sessions[("odoo_demo", 7, "sess-1")] = expired

        self.assertIsNone(store.get(user_id=7, session_id="sess-1", db_name="odoo_demo"))

    def test_clear_removes_scoped_memory(self):
        store = InMemoryStore()
        memory = ConversationMemory(session_id="sess-1")
        store.save(user_id=7, session_id="sess-1", db_name="odoo_demo", memory=memory)

        store.clear(user_id=7, session_id="sess-1", db_name="odoo_demo")

        self.assertIsNone(store.get(user_id=7, session_id="sess-1", db_name="odoo_demo"))

    def test_request_memory_takes_precedence_over_persisted_memory(self):
        persist_memory(
            ConversationMemory(
                session_id="sess-1",
                user_id=7,
                db_name="odoo_demo",
                active_entity=ActiveEntity(type="purchase_order", model="purchase.order", id=113),
            ),
            user_id=7,
            db_name="odoo_demo",
        )

        loaded = load_memory(
            "sess-1",
            {
                "security": {"uid": 7, "db_name": "odoo_demo"},
                "memory": {
                    "active_entity": {
                        "type": "sale_order",
                        "model": "sale.order",
                        "id": 44,
                        "name": "SO-44",
                    }
                },
            },
        )

        self.assertEqual(loaded.active_entity.model, "sale.order")
        self.assertEqual(loaded.active_entity.id, 44)


if __name__ == "__main__":
    unittest.main()
