import unittest

from agents.agent.reference_resolver import resolve_followup, needs_followup_clarification


class TestReferenceResolver(unittest.TestCase):
    def setUp(self):
        self.last_purchase = {
            "model": "purchase.order",
            "id": 99,
            "display_name": "PO-N-00020",
            "fields": {"name": "PO-N-00020"},
        }
        self.last_sale = {
            "model": "sale.order",
            "id": 44,
            "display_name": "SO044",
            "fields": {"name": "SO044"},
        }

    def test_general_invoice_query_should_not_be_forced_as_followup(self):
        question = "dime que facturas estan pendientes y cuales ya se han facturado en este mes"
        self.assertIsNone(resolve_followup(question, self.last_purchase, None))

    def test_short_contextual_invoice_query_should_followup(self):
        question = "facturas?"
        result = resolve_followup(question, self.last_purchase, None)
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("type"), "related_followup")
        self.assertEqual(result.get("intent"), "invoices")

    def test_explicit_reference_should_followup(self):
        question = "y las facturas asociadas a esa compra?"
        result = resolve_followup(question, self.last_purchase, None)
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("type"), "related_followup")
        self.assertEqual(result.get("intent"), "invoices")

    def test_should_ask_clarification_when_related_followup_has_no_context(self):
        question = "muéstrame sus productos"
        result = needs_followup_clarification(question, None, None)
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("type"), "clarification")
        self.assertIn("venta o compra", (result.get("question") or "").lower())

    def test_should_not_ask_clarification_when_context_is_valid(self):
        question = "muéstrame sus productos"
        result = needs_followup_clarification(question, {
            "model": "sale.order",
            "id": 44,
            "display_name": "SO044",
        }, None)
        self.assertIsNone(result)

    def test_related_invoices_uses_outgoing_move_types_for_sales(self):
        result = resolve_followup("facturas?", self.last_sale, None)
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("type"), "related_followup")
        domain = (result.get("search") or {}).get("domain") or []
        self.assertIn(["move_type", "in", ["out_invoice", "out_refund"]], domain)

    def test_related_invoices_uses_incoming_move_types_for_purchases(self):
        result = resolve_followup("facturas?", self.last_purchase, None)
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("type"), "related_followup")
        domain = (result.get("search") or {}).get("domain") or []
        self.assertIn(["move_type", "in", ["in_invoice", "in_refund"]], domain)

    def test_ambiguous_entities_should_request_clarification(self):
        memory = {
            "primary_entity": self.last_sale,
            "last_ui_entity": self.last_sale,
            "last_inferred_entity": self.last_purchase,
            "recent_entities": [
                {"model": "sale.order", "id": 44},
                {"model": "purchase.order", "id": 99},
            ],
        }
        clarification = needs_followup_clarification("tiene alguna factura?", self.last_sale, memory)
        self.assertIsInstance(clarification, dict)
        self.assertEqual(clarification.get("type"), "clarification")
        self.assertTrue(clarification.get("entity_conflict_detected"))
        self.assertEqual(clarification.get("reason"), "ambiguous_recent_entities")

    def test_ambiguous_entities_should_block_auto_resolve(self):
        memory = {
            "primary_entity": self.last_sale,
            "last_ui_entity": self.last_sale,
            "last_inferred_entity": self.last_purchase,
            "recent_entities": [
                {"model": "sale.order", "id": 44},
                {"model": "purchase.order", "id": 99},
            ],
        }
        result = resolve_followup("tiene alguna factura?", self.last_sale, memory)
        self.assertIsNone(result)

    def test_last_explicit_entity_is_preferred_in_followup(self):
        memory = {
            "last_explicit_entity": self.last_purchase,
            "primary_entity": self.last_purchase,
            "last_ui_entity": self.last_sale,
            "recent_entities": [
                {"model": "sale.order", "id": 44},
                {"model": "purchase.order", "id": 99},
            ],
        }
        result = resolve_followup("y esas facturas?", self.last_purchase, memory)
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("source_model"), "purchase.order")
        self.assertEqual(result.get("entity_source_used"), "last_explicit_entity")

    def test_same_model_different_ids_should_not_force_clarification(self):
        memory = {
            "primary_entity": {"model": "sale.order", "id": 77, "display_name": "ID 77"},
            "last_inferred_entity": {"model": "sale.order", "id": 75, "display_name": "DCN 0326-0025"},
            "recent_entities": [
                {"model": "sale.order", "id": 77},
                {"model": "sale.order", "id": 75},
            ],
        }
        clarification = needs_followup_clarification(
            "tiene alguna factura?",
            {"model": "sale.order", "id": 77, "display_name": "ID 77"},
            memory,
        )
        self.assertIsNone(clarification)

    def test_related_sales_from_purchase_followup(self):
        result = resolve_followup("que venta relacionada tiene esa compra?", self.last_purchase, None)
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("type"), "related_followup")
        self.assertEqual(result.get("intent"), "related_sales")
        self.assertEqual((result.get("search") or {}).get("model"), "sale.order")
        domain = (result.get("search") or {}).get("domain") or []
        self.assertIn(["rt_purchase_order", "=", "PO-N-00020"], domain)

    def test_related_sales_without_context_requires_clarification(self):
        clarification = needs_followup_clarification("que venta relacionada tiene esa compra?", None, None)
        self.assertIsInstance(clarification, dict)
        self.assertEqual(clarification.get("type"), "clarification")
        self.assertEqual(clarification.get("intent"), "related_sales")


if __name__ == "__main__":
    unittest.main()
