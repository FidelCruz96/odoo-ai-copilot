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


class TestHybridOrchestrator(unittest.TestCase):
    def test_documentation_route_uses_knowledge_plan(self):
        with patch(
            "app.agents.orchestrator.execute_plan",
            return_value={
                "success": True,
                "tools_used": ["search_knowledge"],
                "results": [
                    {
                        "tool": "search_knowledge",
                        "args": {"query": "politica proceso documentacion"},
                        "result": {
                            "answer": "La política de compras requiere aprobación.",
                            "sources": [{"doc_name": "purchase_approvals.md", "score": 0.9}],
                            "tokens_used": 10,
                        },
                    }
                ],
                "partial_failure": False,
            },
        ) as execute_plan, patch("app.agents.orchestrator.ask_agent") as ask_agent:
            result = ask_hybrid_agent(
                "¿Cómo funciona la política de aprobación de compras?",
                session_id="hybrid-1",
                context={"memory": {}},
                history=[],
            )

        self.assertEqual(result["route_selected"], "knowledge")
        self.assertEqual(result["tools_used"], ["search_knowledge"])
        self.assertTrue(result["grounded"])
        self.assertEqual(result["memory"]["last_sources"], ["purchase_approvals.md"])
        execute_plan.assert_called_once()
        ask_agent.assert_not_called()

    def test_mixed_route_uses_memory_and_both_tools(self):
        with patch(
            "app.agents.orchestrator.execute_plan",
            return_value={
                "success": True,
                "tools_used": ["query_odoo_search", "query_odoo_read"],
                "results": [
                    {"tool": "query_odoo_search", "args": {"model": "purchase.order"}, "result": [113]},
                    {
                        "tool": "query_odoo_read",
                        "args": {"model": "purchase.order"},
                        "result": [
                            {
                                "id": 113,
                                "name": "PO-I-10-00026",
                                "amount_total": 122100.0,
                                "currency_id": [155, "PEN"],
                                "state": "purchase",
                            }
                        ],
                    },
                ],
                "partial_failure": False,
            },
        ):
            first = ask_hybrid_agent(
                "¿Cuánto de monto tiene PO-I-10-00026?",
                session_id="hybrid-2",
                context={"memory": {}},
                history=[],
            )

        with patch(
            "app.agents.orchestrator.execute_plan",
            return_value={
                "success": True,
                "tools_used": ["query_odoo_read", "search_knowledge"],
                "results": [
                    {
                        "tool": "query_odoo_read",
                        "args": {"model": "purchase.order", "ids": [113]},
                        "result": [
                            {
                                "id": 113,
                                "name": "PO-I-10-00026",
                                "amount_total": 122100.0,
                                "currency_id": [155, "PEN"],
                                "state": "purchase",
                            }
                        ],
                    },
                    {
                        "tool": "search_knowledge",
                        "args": {"query": "politica aprobacion compras monto umbral orden de compra"},
                        "result": {
                            "answer": "Compras mayores a S/ 10,000 requieren aprobación.",
                            "sources": [{"doc_name": "purchase_approvals.md", "score": 0.9}],
                            "tokens_used": 20,
                        },
                    },
                ],
                "partial_failure": False,
            },
        ) as execute_plan:
            second = ask_hybrid_agent(
                "¿Debió aprobarse esta compra según la política?",
                session_id="hybrid-2",
                context={"memory": first["memory"]},
                history=[],
            )

        self.assertEqual(second["route_selected"], "mixed")
        self.assertTrue(second["memory_hit"])
        self.assertEqual(second["tools_used"], ["query_odoo_read", "search_knowledge"])
        self.assertTrue(second["grounded"])
        self.assertEqual(second["memory"]["last_sources"], ["purchase_approvals.md"])
        self.assertEqual(second["memory"]["active_entity"]["id"], 113)
        plan = execute_plan.call_args.args[0]
        self.assertEqual(plan[0]["tool"], "query_odoo_read")
        self.assertEqual(plan[1]["tool"], "search_knowledge")

    def test_clarification_route_does_not_call_tools(self):
        with patch("app.agents.orchestrator.execute_plan") as execute_plan, patch(
            "app.agents.orchestrator.ask_agent"
        ) as ask_agent:
            result = ask_hybrid_agent(
                "¿Debió aprobarse esta compra según la política?",
                session_id="hybrid-3",
                context={"memory": {}},
                history=[],
            )

        self.assertEqual(result["route_selected"], "clarification")
        self.assertTrue(result["needs_clarification"])
        self.assertEqual(result["tools_used"], [])
        self.assertIn("PO-I-10-00026", result["answer"])
        execute_plan.assert_not_called()
        ask_agent.assert_not_called()

    def test_mixed_route_with_explicit_entity_reads_and_queries_policy(self):
        with patch(
            "app.agents.orchestrator.execute_plan",
            return_value={
                "success": True,
                "tools_used": ["query_odoo_search", "query_odoo_read", "search_knowledge"],
                "results": [
                    {"tool": "query_odoo_search", "args": {"model": "purchase.order"}, "result": [45]},
                    {
                        "tool": "query_odoo_read",
                        "args": {"model": "purchase.order", "ids": [45]},
                        "result": [{"id": 45, "name": "PO00045", "amount_total": 12500.0, "currency_id": [155, "PEN"], "state": "purchase"}],
                    },
                    {
                        "tool": "search_knowledge",
                        "args": {"query": "politica aprobacion compras monto umbral orden de compra"},
                        "result": {
                            "answer": "Compras mayores a S/ 10,000 requieren aprobación.",
                            "sources": [{"doc_name": "purchase_approvals.md", "score": 0.92}],
                            "tokens_used": 18,
                        },
                    },
                ],
                "partial_failure": False,
            },
        ) as execute_plan:
            result = ask_hybrid_agent(
                "¿La compra PO00045 debió aprobarse según la política?",
                session_id="hybrid-4",
                context={"memory": {}},
                history=[],
            )

        self.assertEqual(result["route_selected"], "mixed")
        self.assertEqual(result["sources"][0]["doc_name"], "purchase_approvals.md")
        self.assertIn("PO00045", result["answer"])
        plan = execute_plan.call_args.args[0]
        self.assertEqual(plan[0]["tool"], "query_odoo_search")
        self.assertEqual(plan[1]["tool"], "query_odoo_read")
        self.assertEqual(plan[2]["tool"], "search_knowledge")


if __name__ == "__main__":
    unittest.main()
