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


from app.memory.memory_store import get_store, load_memory, persist_memory
from app.memory.schemas import ActiveEntity, ConversationMemory


class TestMemoryLoading(unittest.TestCase):
    def setUp(self):
        get_store()._sessions.clear()

    def test_empty_context_memory_falls_back_to_session_store(self):
        persist_memory(
            ConversationMemory(
                session_id="sess-1",
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
            )
        )

        loaded = load_memory("sess-1", {"memory": {}})

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.active_entity.id, 113)
        self.assertEqual(loaded.last_route, "erp_data")


if __name__ == "__main__":
    unittest.main()
