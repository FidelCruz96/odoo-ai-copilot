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
    psycopg2_extras_stub.execute_batch = lambda *args, **kwargs: None
    psycopg2_stub.extras = psycopg2_extras_stub
    sys.modules["psycopg2"] = psycopg2_stub
    sys.modules["psycopg2.extras"] = psycopg2_extras_stub

from app.agents.orchestrator import ask_hybrid_agent


class TestOrchestratorFlow(unittest.TestCase):
    def _tool_side_effect(self, **kwargs):
        raise AssertionError("Unexpected direct call")

    def test_amount_lookup_explicit_po(self):
        with patch("app.agents.orchestrator.execute_plan", return_value={
            "success": True,
            "tools_used": ["query_odoo_search", "query_odoo_read"],
            "results": [
                {"tool": "query_odoo_search", "args": {"model": "purchase.order"}, "result": [113]},
                {"tool": "query_odoo_read", "args": {"model": "purchase.order"}, "result": [{"id": 113, "name": "PO-I-10-00026", "amount_total": 122100.0, "currency_id": [155, "PEN"], "state": "purchase"}]},
            ],
            "partial_failure": False,
        }):
            result = ask_hybrid_agent("¿Cuánto de monto tiene PO-I-10-00026?", session_id="flow-1", context={"memory": {}}, history=[])

        self.assertEqual(result["domain_detected"], "purchase")
        self.assertEqual(result["intent_detected"], "amount_lookup")
        self.assertEqual(result["route_selected"], "erp_data")
        self.assertEqual(result["tools_used"], ["query_odoo_search", "query_odoo_read"])
        self.assertTrue(result["grounded"])
        self.assertTrue(result["memory_updated"])
        self.assertEqual(result["active_model"], "purchase.order")
        self.assertEqual(result["active_id"], 113)
        self.assertEqual(result["metrics"]["route_selected"], "erp_data")
        self.assertEqual(result["metrics"]["domain_detected"], "purchase")
        self.assertEqual(result["metrics"]["intent_detected"], "amount_lookup")
        self.assertEqual(result["metrics"]["active_id"], 113)

    def test_followup_policy_validation_uses_memory(self):
        with patch("app.agents.orchestrator.execute_plan", return_value={
            "success": True,
            "tools_used": ["query_odoo_search", "query_odoo_read"],
            "results": [
                {"tool": "query_odoo_search", "args": {"model": "purchase.order"}, "result": [113]},
                {"tool": "query_odoo_read", "args": {"model": "purchase.order"}, "result": [{"id": 113, "name": "PO-I-10-00026", "amount_total": 122100.0, "currency_id": [155, "PEN"], "state": "purchase"}]},
            ],
            "partial_failure": False,
        }):
            first = ask_hybrid_agent("¿Cuánto de monto tiene PO-I-10-00026?", session_id="flow-2", context={"memory": {}}, history=[])

        with patch("app.agents.orchestrator.execute_plan", return_value={
            "success": True,
            "tools_used": ["query_odoo_read", "search_knowledge"],
            "results": [
                {"tool": "query_odoo_read", "args": {"model": "purchase.order"}, "result": [{"id": 113, "name": "PO-I-10-00026", "amount_total": 122100.0, "currency_id": [155, "PEN"], "state": "purchase"}]},
                {"tool": "search_knowledge", "args": {"query": "politica aprobacion compras monto umbral orden de compra"}, "result": {"answer": "Compras mayores a S/ 10,000 requieren aprobación.", "sources": [{"doc_name": "purchase_approvals.md", "score": 0.9}], "tokens_used": 20}},
            ],
            "partial_failure": False,
        }):
            second = ask_hybrid_agent("¿Debió aprobarse esta compra según la política?", session_id="flow-2", context={"memory": first["memory"]}, history=[])

        self.assertEqual(second["route_selected"], "mixed")
        self.assertTrue(second["memory_hit"])
        self.assertEqual(second["tools_used"], ["query_odoo_read", "search_knowledge"])
        self.assertTrue(second["grounded"])
        self.assertTrue(second["sources"])
        self.assertEqual(second["metrics"]["route_selected"], "mixed")
        self.assertTrue(second["metrics"]["memory_hit"])

    def test_relative_reference_without_memory(self):
        result = ask_hybrid_agent("¿Debió aprobarse esta compra según la política?", session_id="flow-3", context={"memory": {}}, history=[])
        self.assertEqual(result["route_selected"], "clarification")
        self.assertTrue(result["needs_clarification"])

    def test_documentation_pure(self):
        with patch("app.agents.orchestrator.execute_plan", return_value={
            "success": True,
            "tools_used": ["search_knowledge"],
            "results": [
                {"tool": "search_knowledge", "args": {"query": "politica proceso documentacion"}, "result": {"answer": "La política de compras requiere aprobación.", "sources": [{"doc_name": "purchase_approvals.md", "score": 0.9}], "tokens_used": 10}},
            ],
            "partial_failure": False,
        }):
            result = ask_hybrid_agent("¿Cómo funciona la política de aprobación de compras?", session_id="flow-4", context={"memory": {}}, history=[])
        self.assertEqual(result["route_selected"], "knowledge")
        self.assertEqual(result["tools_used"], ["search_knowledge"])
        self.assertTrue(result["grounded"])
        self.assertEqual(result["metrics"]["route_selected"], "knowledge")
        self.assertEqual(result["metrics"]["tools_used"], ["search_knowledge"])

    def test_sale_amount_lookup_with_business_code_hint(self):
        with patch("app.agents.orchestrator.execute_plan", return_value={
            "success": True,
            "tools_used": ["query_odoo_search", "query_odoo_read"],
            "results": [
                {"tool": "query_odoo_search", "args": {"model": "sale.order"}, "result": [44]},
                {"tool": "query_odoo_read", "args": {"model": "sale.order"}, "result": [{"id": 44, "name": "DCN 0426-0039", "amount_total": 66937.86, "currency_id": [1, "USD"], "state": "sale"}]},
            ],
            "partial_failure": False,
        }):
            result = ask_hybrid_agent("cuanto de monto tiene la venta DCN 0426-0039?", session_id="flow-5", context={"memory": {}}, history=[])

        self.assertEqual(result["route_selected"], "erp_data")
        self.assertEqual(result["domain_detected"], "sale")
        self.assertEqual(result["active_model"], "sale.order")
        self.assertTrue(result["grounded"])

    def test_explicit_business_code_without_domain_does_not_reuse_purchase_memory(self):
        with patch("app.agents.orchestrator.execute_plan", return_value={
            "success": True,
            "tools_used": ["query_odoo_search", "query_odoo_read"],
            "results": [
                {"tool": "query_odoo_search", "args": {"model": "purchase.order"}, "result": [113]},
                {"tool": "query_odoo_read", "args": {"model": "purchase.order"}, "result": [{"id": 113, "name": "PO-I-10-00026", "amount_total": 122100.0, "currency_id": [155, "PEN"], "state": "purchase"}]},
            ],
            "partial_failure": False,
        }):
            first = ask_hybrid_agent("¿Cuánto de monto tiene PO-I-10-00026?", session_id="flow-6", context={"memory": {}}, history=[])

        second = ask_hybrid_agent("DCN 0426-0039", session_id="flow-6", context={"memory": first["memory"]}, history=[])

        self.assertEqual(second["route_selected"], "clarification")
        self.assertTrue(second["needs_clarification"])
        self.assertFalse(second["memory_hit"])


if __name__ == "__main__":
    unittest.main()
