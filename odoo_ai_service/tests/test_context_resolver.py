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

from app.agents.context_resolver import resolve_context
from app.memory.schemas import ActiveEntity, ConversationMemory


class TestContextResolver(unittest.TestCase):
    def test_relative_reference_uses_memory(self):
        memory = ConversationMemory(
            session_id="s1",
            active_entity=ActiveEntity(type="purchase_order", model="purchase.order", id=113, name="PO-I-10-00026"),
        )
        resolved = resolve_context({"type": "relative_reference", "target_domain": "purchase"}, memory)
        self.assertTrue(resolved["memory_hit"])
        self.assertEqual(resolved["entity"]["id"], 113)

    def test_relative_reference_without_memory_requires_clarification(self):
        resolved = resolve_context({"type": "relative_reference", "target_domain": "purchase"}, None)
        self.assertTrue(resolved["needs_clarification"])

    def test_explicit_business_code_without_domain_requires_clarification(self):
        memory = ConversationMemory(
            session_id="s2",
            active_entity=ActiveEntity(type="purchase_order", model="purchase.order", id=113, name="PO-I-10-00026"),
        )
        resolved = resolve_context({"type": "business_document_code", "code": "DCN 0426-0039"}, memory)
        self.assertTrue(resolved["needs_clarification"])
        self.assertFalse(resolved["memory_hit"])


if __name__ == "__main__":
    unittest.main()
