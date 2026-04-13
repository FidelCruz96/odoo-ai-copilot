import unittest

from agents.agent.clarification_resolver import detect_clarification_needed, resolve_pending_clarification


class TestClarificationResolver(unittest.TestCase):
    def test_sales_vs_invoices_asks_when_ambiguous(self):
        result = detect_clarification_needed("muéstrame las ventas pendientes", memory={})
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("name"), "sales_vs_invoices_scope")

    def test_sales_vs_invoices_does_not_ask_when_invoice_is_explicit(self):
        result = detect_clarification_needed("muéstrame las facturas pendientes", memory={})
        self.assertIsNone(result)

    def test_sales_vs_invoices_resolution_rewrites_question(self):
        memory = {
            "pending_clarification": {
                "name": "sales_vs_invoices_scope",
                "question": "¿Te refieres a pedidos de venta o a facturas emitidas?",
                "original_question": "muéstrame las ventas pendientes",
            }
        }
        result = resolve_pending_clarification("facturas emitidas", memory)
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("resolved"))
        self.assertIn("facturas emitidas", result.get("rewritten_question", ""))

    def test_count_vs_list_asks_when_action_is_ambiguous(self):
        result = detect_clarification_needed("facturas pendientes este mes", memory={})
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("name"), "count_vs_list_scope")

    def test_count_vs_list_does_not_ask_when_count_is_explicit(self):
        result = detect_clarification_needed("cuántas facturas pendientes hay este mes", memory={})
        self.assertIsNone(result)

    def test_count_vs_list_resolution_to_detail(self):
        memory = {
            "pending_clarification": {
                "name": "count_vs_list_scope",
                "question": "¿Quieres solo el total o quieres ver el detalle?",
                "original_question": "facturas pendientes este mes",
            }
        }
        result = resolve_pending_clarification("detalle", memory)
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("resolved"))
        self.assertIn("detalle", result.get("rewritten_question", ""))


if __name__ == "__main__":
    unittest.main()
