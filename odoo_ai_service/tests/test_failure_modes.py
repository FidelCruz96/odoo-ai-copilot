import sys
import types
import unittest
from unittest.mock import patch


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

if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")
    openai_stub.OpenAI = object
    openai_stub.RateLimitError = Exception
    openai_stub.APIError = Exception
    openai_stub.APIConnectionError = Exception
    sys.modules["openai"] = openai_stub

if "psycopg2" not in sys.modules:
    psycopg2_stub = types.ModuleType("psycopg2")
    psycopg2_extras_stub = types.ModuleType("psycopg2.extras")
    psycopg2_stub.connect = lambda *args, **kwargs: None
    psycopg2_extras_stub.RealDictCursor = object
    psycopg2_stub.extras = psycopg2_extras_stub
    sys.modules["psycopg2"] = psycopg2_stub
    sys.modules["psycopg2.extras"] = psycopg2_extras_stub

from app.agents.orchestrator import ask_hybrid_agent
from app.memory import memory_store


class TestFailureModes(unittest.TestCase):
    def setUp(self):
        memory_store.reset_store_for_tests()

    def test_odoo_tool_error_returns_controlled_response(self):
        with patch(
            "app.agents.orchestrator.execute_plan",
            return_value={
                "success": False,
                "tools_used": ["query_odoo_count"],
                "results": [
                    {"tool": "query_odoo_count", "args": {"model": "sale.order"}, "result": {"error": "odoo_http_500"}},
                ],
                "partial_failure": True,
                "error_type": "odoo_http_500",
                "message": "Error ejecutando query_odoo_count: odoo_http_500",
            },
        ):
            result = ask_hybrid_agent("cuantas ventas hay", session_id="fail-odoo", context={"memory": {}}, history=[])

        self.assertEqual(result["route_selected"], "erp_data")
        self.assertFalse(result["grounded"])
        self.assertFalse(result["response_faithful"])
        self.assertEqual(result["error_type"], "odoo_http_500")
        self.assertTrue(result["partial_failure"])

    def test_rag_without_sources_is_not_grounded(self):
        with patch(
            "app.agents.orchestrator.execute_plan",
            return_value={
                "success": True,
                "tools_used": ["search_knowledge"],
                "results": [
                    {
                        "tool": "search_knowledge",
                        "args": {"query": "politica"},
                        "result": {
                            "answer": "No encontré suficiente contexto documental.",
                            "sources": [],
                            "tokens_used": 0,
                        },
                    }
                ],
                "partial_failure": False,
            },
        ):
            result = ask_hybrid_agent("como funciona la politica de compras", session_id="fail-rag", context={"memory": {}}, history=[])

        self.assertEqual(result["route_selected"], "knowledge")
        self.assertFalse(result["grounded"])
        self.assertFalse(result["response_faithful"])
        self.assertEqual(result["sources"], [])

    def test_memory_store_failure_does_not_crash_request(self):
        class BrokenStore:
            def get(self, **kwargs):
                raise RuntimeError("db down")

            def save(self, **kwargs):
                raise RuntimeError("db down")

            def clear(self, **kwargs):
                raise RuntimeError("db down")

        memory_store.reset_store_for_tests(BrokenStore())

        with patch(
            "app.agents.orchestrator.execute_plan",
            return_value={
                "success": True,
                "tools_used": ["query_odoo_count"],
                "results": [{"tool": "query_odoo_count", "args": {"model": "sale.order"}, "result": 4}],
                "partial_failure": False,
            },
        ):
            result = ask_hybrid_agent("cuantas ventas hay", session_id="fail-memory", context={"memory": {}}, history=[])

        self.assertEqual(result["route_selected"], "erp_data")
        self.assertTrue(result["grounded"])
        self.assertFalse(result["memory_hit"])


if __name__ == "__main__":
    unittest.main()
