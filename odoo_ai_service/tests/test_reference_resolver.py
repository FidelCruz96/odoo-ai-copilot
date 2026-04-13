import unittest

from agents.agent.reference_resolver import resolve_followup


class TestReferenceResolver(unittest.TestCase):
    def setUp(self):
        self.last_purchase = {
            "model": "purchase.order",
            "id": 99,
            "display_name": "PO-N-00020",
            "fields": {"name": "PO-N-00020"},
        }

    def test_general_invoice_query_should_not_be_forced_as_followup(self):
        question = "dime que facturas estan pendientes y cuales ya se han facturado en este mes"
        self.assertIsNone(resolve_followup(question, self.last_purchase))

    def test_short_contextual_invoice_query_should_followup(self):
        question = "facturas?"
        result = resolve_followup(question, self.last_purchase)
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("type"), "related_followup")
        self.assertEqual(result.get("intent"), "invoices")

    def test_explicit_reference_should_followup(self):
        question = "y las facturas asociadas a esa compra?"
        result = resolve_followup(question, self.last_purchase)
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("type"), "related_followup")
        self.assertEqual(result.get("intent"), "invoices")


if __name__ == "__main__":
    unittest.main()
