import unittest

from app.agents.router import HybridRoute, classify_route
from app.agents.response_composer import build_odoo_evidence, compose_response


class TestHybridRouter(unittest.TestCase):
    def test_documentation_route(self):
        self.assertEqual(classify_route("¿Qué es un picking?"), HybridRoute.DOCUMENTATION)

    def test_erp_route(self):
        self.assertEqual(classify_route("Top clientes por facturación este mes"), HybridRoute.ERP_DATA)

    def test_mixed_route(self):
        self.assertEqual(
            classify_route("¿Esta compra debió aprobarse según la política?"),
            HybridRoute.MIXED,
        )

    def test_clarification_route(self):
        self.assertEqual(classify_route("Pendientes"), HybridRoute.CLARIFICATION)

    def test_compose_mixed_response(self):
        knowledge = {
            "answer": "La política indica aprobación sobre S/ 10,000.",
            "sources": [{"doc_name": "purchase_approvals.md", "score": 0.84, "page": None}],
        }
        erp_result = {
            "answer": "La compra PO00045 tiene monto S/ 12,500 y estado purchase.",
            "metadata": {
                "tool_trace": [
                    {
                        "tool": "query_odoo_read",
                        "model": "purchase.order",
                        "domain": [["name", "=", "PO00045"]],
                        "fields": ["name", "amount_total", "state"],
                    }
                ]
            },
        }
        answer = compose_response(HybridRoute.MIXED, knowledge_result=knowledge, erp_result=erp_result)
        self.assertIn("Fuentes documentales", answer)
        self.assertIn("purchase.order", answer)
        evidence = build_odoo_evidence(erp_result)
        self.assertEqual(evidence[0]["model"], "purchase.order")


if __name__ == "__main__":
    unittest.main()
