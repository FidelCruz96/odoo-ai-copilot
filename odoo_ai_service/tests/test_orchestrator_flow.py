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
from app.memory.memory_store import reset_store_for_tests


PURCHASE_MEMORY = {
    "active_entity": {
        "type": "purchase_order",
        "model": "purchase.order",
        "id": 113,
        "name": "PO-I-10-00026",
        "confidence": 1.0,
    }
}


class TestOrchestratorFlow(unittest.TestCase):
    def setUp(self):
        reset_store_for_tests()

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

    def test_line_items_without_active_entity_asks_for_clarification(self):
        result = ask_hybrid_agent("que productos se vendieron", session_id="flow-lines", context={"memory": {}}, history=[])

        self.assertEqual(result["route_selected"], "clarification")
        self.assertEqual(result["intent_detected"], "line_items")
        self.assertTrue(result["needs_clarification"])
        self.assertIn("venta", result["answer"].lower())
        self.assertEqual(result["tools_used"], [])

    def test_amount_without_active_entity_asks_for_clarification(self):
        result = ask_hybrid_agent("cuanto es el total", session_id="flow-amount-missing", context={"memory": {}}, history=[])

        self.assertEqual(result["route_selected"], "clarification")
        self.assertEqual(result["intent_detected"], "amount_lookup")
        self.assertTrue(result["needs_clarification"])
        self.assertIn("contexto", result["answer"].lower())

    def test_status_without_active_entity_asks_for_clarification(self):
        result = ask_hybrid_agent("cual es su estado", session_id="flow-status-missing", context={"memory": {}}, history=[])

        self.assertEqual(result["route_selected"], "clarification")
        self.assertEqual(result["intent_detected"], "status_lookup")
        self.assertTrue(result["needs_clarification"])
        self.assertIn("contexto", result["answer"].lower())

    def test_status_uses_active_ui_purchase_context(self):
        with patch("app.agents.orchestrator.execute_plan", return_value={
            "success": True,
            "tools_used": ["query_odoo_read"],
            "results": [
                {"tool": "query_odoo_read", "args": {"model": "purchase.order"}, "result": [{"id": 11, "name": "P00011", "state": "purchase"}]},
            ],
            "partial_failure": False,
        }) as execute_plan:
            result = ask_hybrid_agent(
                "en que estado esta la compra?",
                session_id="flow-ui-active-status",
                context={
                    "memory": {},
                    "client": {
                        "active_model": "purchase.order",
                        "active_id": 11,
                    },
                },
                history=[],
            )

        self.assertEqual(result["route_selected"], "erp_data")
        self.assertEqual(result["intent_detected"], "status_lookup")
        self.assertTrue(result["memory_hit"])
        self.assertEqual(result["active_model"], "purchase.order")
        self.assertEqual(result["active_id"], 11)
        self.assertEqual(execute_plan.call_args.args[0][0]["tool"], "query_odoo_read")
        self.assertEqual(execute_plan.call_args.args[0][0]["args"]["ids"], [11])

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

    def test_sale_count_uses_odoo_count_tool(self):
        with patch("app.agents.orchestrator.execute_plan", return_value={
            "success": True,
            "tools_used": ["query_odoo_count"],
            "results": [
                {"tool": "query_odoo_count", "args": {"model": "sale.order"}, "result": 24},
            ],
            "partial_failure": False,
        }) as execute_plan:
            result = ask_hybrid_agent("cuantas ventas hay", session_id="flow-count", context={"memory": {}}, history=[])

        self.assertEqual(result["route_selected"], "erp_data")
        self.assertEqual(result["tools_used"], ["query_odoo_count"])
        self.assertTrue(result["grounded"])
        self.assertIn("24 ventas", result["answer"])
        self.assertEqual(execute_plan.call_args.args[0][0]["tool"], "query_odoo_count")
        self.assertEqual(execute_plan.call_args.kwargs["context"]["request_id"], result["trace_id"])

    def test_invoice_ranking_uses_odoo_group_tool(self):
        with patch("app.agents.orchestrator.execute_plan", return_value={
            "success": True,
            "tools_used": ["query_odoo_group"],
            "results": [
                {
                    "tool": "query_odoo_group",
                    "args": {"model": "account.move"},
                    "result": [{"partner_id": [1, "Cliente A"], "amount_total": 100.0}],
                },
            ],
            "partial_failure": False,
        }) as execute_plan:
            result = ask_hybrid_agent("top clientes por facturacion", session_id="flow-rank", context={"memory": {}}, history=[])

        self.assertEqual(result["route_selected"], "erp_data")
        self.assertEqual(result["tools_used"], ["query_odoo_group"])
        self.assertTrue(result["grounded"])
        self.assertIn("Cliente A", result["answer"])
        self.assertEqual(execute_plan.call_args.args[0][0]["tool"], "query_odoo_group")

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

    def test_memory_does_not_contaminate_sale_count(self):
        with patch("app.agents.orchestrator.execute_plan", return_value={
            "success": True,
            "tools_used": ["query_odoo_count"],
            "results": [
                {"tool": "query_odoo_count", "args": {"model": "sale.order"}, "result": 24},
            ],
            "partial_failure": False,
        }) as execute_plan:
            result = ask_hybrid_agent("cuantas ventas hay", session_id="flow-memory-count", context={"memory": PURCHASE_MEMORY}, history=[])

        self.assertEqual(result["route_selected"], "erp_data")
        self.assertEqual(result["domain_detected"], "sale")
        self.assertEqual(result["intent_detected"], "count")
        self.assertFalse(result["memory_hit"])
        self.assertEqual(execute_plan.call_args.args[0][0]["args"]["model"], "sale.order")

    def test_memory_does_not_contaminate_invoice_ranking(self):
        with patch("app.agents.orchestrator.execute_plan", return_value={
            "success": True,
            "tools_used": ["query_odoo_group"],
            "results": [
                {"tool": "query_odoo_group", "args": {"model": "account.move"}, "result": [{"partner_id": [1, "Cliente A"], "amount_total": 100.0}]},
            ],
            "partial_failure": False,
        }) as execute_plan:
            result = ask_hybrid_agent("top clientes por facturacion", session_id="flow-memory-rank", context={"memory": PURCHASE_MEMORY}, history=[])

        self.assertEqual(result["route_selected"], "erp_data")
        self.assertEqual(result["domain_detected"], "invoice")
        self.assertEqual(result["intent_detected"], "ranking")
        self.assertFalse(result["memory_hit"])
        self.assertEqual(execute_plan.call_args.args[0][0]["args"]["model"], "account.move")

    def test_amount_total_uses_memory_when_contextual(self):
        with patch("app.agents.orchestrator.execute_plan", return_value={
            "success": True,
            "tools_used": ["query_odoo_read"],
            "results": [
                {"tool": "query_odoo_read", "args": {"model": "purchase.order"}, "result": [{"id": 113, "name": "PO-I-10-00026", "amount_total": 122100.0, "currency_id": [155, "PEN"], "state": "purchase"}]},
            ],
            "partial_failure": False,
        }) as execute_plan:
            result = ask_hybrid_agent("cuanto es el total", session_id="flow-memory-amount", context={"memory": PURCHASE_MEMORY}, history=[])

        self.assertEqual(result["route_selected"], "erp_data")
        self.assertTrue(result["memory_hit"])
        self.assertEqual(result["active_model"], "purchase.order")
        self.assertEqual(execute_plan.call_args.args[0][0]["tool"], "query_odoo_read")

    def test_relative_policy_uses_memory_for_mixed_route(self):
        with patch("app.agents.orchestrator.execute_plan", return_value={
            "success": True,
            "tools_used": ["query_odoo_read", "search_knowledge"],
            "results": [
                {"tool": "query_odoo_read", "args": {"model": "purchase.order"}, "result": [{"id": 113, "name": "PO-I-10-00026", "amount_total": 122100.0, "currency_id": [155, "PEN"], "state": "purchase"}]},
                {"tool": "search_knowledge", "args": {"query": "esta compra requiere aprobacion politica aprobacion compras monto umbral orden de compra"}, "result": {"answer": "Requiere aprobación.", "sources": [{"doc_name": "purchase_approvals.md", "score": 0.9}], "tokens_used": 20}},
            ],
            "partial_failure": False,
        }) as execute_plan:
            result = ask_hybrid_agent("esta compra requiere aprobacion?", session_id="flow-memory-policy", context={"memory": PURCHASE_MEMORY}, history=[])

        self.assertEqual(result["route_selected"], "mixed")
        self.assertEqual(result["intent_detected"], "policy_validation")
        self.assertTrue(result["memory_hit"])
        self.assertEqual(result["tools_used"], ["query_odoo_read", "search_knowledge"])
        self.assertTrue(result["sources"])
        self.assertEqual([step["tool"] for step in execute_plan.call_args.args[0]], ["query_odoo_read", "search_knowledge"])

    def test_relative_policy_uses_persisted_memory_when_request_memory_is_empty(self):
        scoped_context = {"security": {"uid": 7, "db_name": "odoo_demo"}, "memory": {}}
        with patch("app.agents.orchestrator.execute_plan", return_value={
            "success": True,
            "tools_used": ["query_odoo_search", "query_odoo_read"],
            "results": [
                {"tool": "query_odoo_search", "args": {"model": "purchase.order"}, "result": [113]},
                {"tool": "query_odoo_read", "args": {"model": "purchase.order"}, "result": [{"id": 113, "name": "PO-I-10-00026", "amount_total": 122100.0, "currency_id": [155, "PEN"], "state": "purchase"}]},
            ],
            "partial_failure": False,
        }):
            first = ask_hybrid_agent("¿Cuánto de monto tiene PO-I-10-00026?", session_id="flow-persisted-memory", context=scoped_context, history=[])

        self.assertTrue(first["memory_updated"])

        with patch("app.agents.orchestrator.execute_plan", return_value={
            "success": True,
            "tools_used": ["query_odoo_read", "search_knowledge"],
            "results": [
                {"tool": "query_odoo_read", "args": {"model": "purchase.order"}, "result": [{"id": 113, "name": "PO-I-10-00026", "amount_total": 122100.0, "currency_id": [155, "PEN"], "state": "purchase"}]},
                {"tool": "search_knowledge", "args": {"query": "esta compra requiere aprobacion politica aprobacion compras monto umbral orden de compra"}, "result": {"answer": "Requiere aprobación.", "sources": [{"doc_name": "purchase_approvals.md", "score": 0.9}], "tokens_used": 20}},
            ],
            "partial_failure": False,
        }):
            second = ask_hybrid_agent("esta compra requiere aprobacion?", session_id="flow-persisted-memory", context=scoped_context, history=[])

        self.assertEqual(second["route_selected"], "mixed")
        self.assertTrue(second["memory_hit"])
        self.assertEqual(second["active_model"], "purchase.order")

    def test_persisted_memory_is_scoped_by_user(self):
        with patch("app.agents.orchestrator.execute_plan", return_value={
            "success": True,
            "tools_used": ["query_odoo_search", "query_odoo_read"],
            "results": [
                {"tool": "query_odoo_search", "args": {"model": "purchase.order"}, "result": [113]},
                {"tool": "query_odoo_read", "args": {"model": "purchase.order"}, "result": [{"id": 113, "name": "PO-I-10-00026", "amount_total": 122100.0, "currency_id": [155, "PEN"], "state": "purchase"}]},
            ],
            "partial_failure": False,
        }):
            ask_hybrid_agent(
                "¿Cuánto de monto tiene PO-I-10-00026?",
                session_id="flow-user-scope",
                context={"security": {"uid": 7, "db_name": "odoo_demo"}, "memory": {}},
                history=[],
            )

        with patch("app.agents.orchestrator.execute_plan") as execute_plan:
            result = ask_hybrid_agent(
                "esta compra requiere aprobacion?",
                session_id="flow-user-scope",
                context={"security": {"uid": 8, "db_name": "odoo_demo"}, "memory": {}},
                history=[],
            )

        self.assertEqual(result["route_selected"], "clarification")
        self.assertFalse(result["memory_hit"])
        execute_plan.assert_not_called()

    def test_relative_policy_without_memory_asks_for_clarification(self):
        with patch("app.agents.orchestrator.execute_plan") as execute_plan:
            result = ask_hybrid_agent("esta compra requiere aprobacion?", session_id="flow-no-memory-policy", context={"memory": {}}, history=[])

        self.assertEqual(result["route_selected"], "clarification")
        self.assertTrue(result["needs_clarification"])
        execute_plan.assert_not_called()

    def test_ambiguous_period_metric_clarifies_instead_of_legacy_tool(self):
        result = ask_hybrid_agent("ventas del mes", session_id="flow-period-ambiguous", context={"memory": {}}, history=[])

        self.assertEqual(result["route_selected"], "clarification")
        self.assertTrue(result["needs_clarification"])
        self.assertEqual(result["tools_used"], [])
        self.assertIn("cantidad", result["answer"].lower())

    def test_odoo_evidence_uses_real_result_sample(self):
        with patch("app.agents.orchestrator.execute_plan", return_value={
            "success": True,
            "tools_used": ["query_odoo_search", "query_odoo_read"],
            "results": [
                {"tool": "query_odoo_search", "args": {"model": "purchase.order"}, "result": [113]},
                {"tool": "query_odoo_read", "args": {"model": "purchase.order"}, "result": [{
                    "id": 113,
                    "name": "PO-I-10-00026",
                    "amount_total": 122100.0,
                    "state": "purchase",
                    "token": "hidden",
                    "secret": "hidden",
                    "password": "hidden",
                }]},
            ],
            "partial_failure": False,
        }):
            result = ask_hybrid_agent("¿Cuánto de monto tiene PO-I-10-00026?", session_id="flow-evidence", context={"memory": {}}, history=[])

        evidence = result["odoo_evidence"][0]["result_sample"][0]
        self.assertEqual(evidence["id"], 113)
        self.assertEqual(evidence["name"], "PO-I-10-00026")
        self.assertEqual(evidence["amount_total"], 122100.0)
        self.assertEqual(evidence["state"], "purchase")
        self.assertNotIn("password", evidence)
        self.assertNotIn("token", evidence)
        self.assertNotIn("secret", evidence)


if __name__ == "__main__":
    unittest.main()
