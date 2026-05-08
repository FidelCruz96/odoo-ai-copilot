import sys
import types
import unittest
from unittest.mock import patch

if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")

    class DummyOpenAI:
        def __init__(self, *args, **kwargs):
            pass

    openai_stub.OpenAI = DummyOpenAI
    openai_stub.RateLimitError = Exception
    openai_stub.APIError = Exception
    openai_stub.APIConnectionError = Exception
    sys.modules["openai"] = openai_stub

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

if "psycopg2" not in sys.modules:
    psycopg2_stub = types.ModuleType("psycopg2")
    psycopg2_extras_stub = types.ModuleType("psycopg2.extras")

    def connect(*args, **kwargs):
        raise RuntimeError("psycopg2 stub should not be used in unit tests")

    class RealDictCursor:
        pass

    def execute_batch(*args, **kwargs):
        return None

    psycopg2_stub.connect = connect
    psycopg2_extras_stub.RealDictCursor = RealDictCursor
    psycopg2_extras_stub.execute_batch = execute_batch
    psycopg2_stub.extras = psycopg2_extras_stub
    sys.modules["psycopg2"] = psycopg2_stub
    sys.modules["psycopg2.extras"] = psycopg2_extras_stub

from app.agents import tool_executor


class TestAppToolExecutorMessages(unittest.TestCase):
    def test_empty_search_uses_model_specific_entity_label(self):
        plan = [{"tool": "query_odoo_search", "args": {"model": "sale.order"}}]
        registry = dict(tool_executor.TOOL_REGISTRY)
        registry["query_odoo_search"] = lambda **kwargs: []

        with patch.object(tool_executor, "TOOL_REGISTRY", registry):
            result = tool_executor.execute_plan(plan, entity={"model": "sale.order", "code": "SO001"})

        self.assertFalse(result["success"])
        self.assertEqual(result["message"], "No encontré la venta SO001.")

    def test_missing_read_ids_uses_model_specific_entity_label(self):
        plan = [{"tool": "query_odoo_read", "args": {"model": "account.move", "ids": []}}]

        result = tool_executor.execute_plan(plan, entity={"model": "account.move", "code": "INV001"})

        self.assertFalse(result["success"])
        self.assertEqual(result["message"], "No encontré la factura INV001.")

    def test_odoo_tool_receives_runtime_context(self):
        plan = [{"tool": "query_odoo_count", "args": {"model": "sale.order", "domain": []}}]
        registry = dict(tool_executor.TOOL_REGISTRY)
        captured = {}

        def fake_count(**kwargs):
            captured.update(kwargs)
            return 7

        registry["query_odoo_count"] = fake_count
        context = {"request_id": "req-iam", "security": {"uid": 9, "company_ids": [1]}}

        with patch.object(tool_executor, "TOOL_REGISTRY", registry):
            result = tool_executor.execute_plan(plan, context=context)

        self.assertTrue(result["success"])
        self.assertEqual(result["results"][0]["result"], 7)
        self.assertEqual(captured["context"], context)
        self.assertNotIn("context", result["results"][0]["args"])
        self.assertEqual(result["trace_id"], "req-iam")

    def test_tool_exception_returns_structured_error_with_trace_id(self):
        plan = [{"tool": "query_odoo_count", "args": {"model": "sale.order", "domain": []}}]
        registry = dict(tool_executor.TOOL_REGISTRY)

        def failing_count(**kwargs):
            raise RuntimeError("boom")

        registry["query_odoo_count"] = failing_count
        context = {"request_id": "req-fail", "security": {"uid": 9, "company_ids": [1]}}

        with patch.object(tool_executor, "TOOL_REGISTRY", registry):
            result = tool_executor.execute_plan(plan, context=context)

        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "tool_exception")
        self.assertEqual(result["trace_id"], "req-fail")
        self.assertIn("Trace ID: req-fail", result["message"])


if __name__ == "__main__":
    unittest.main()
