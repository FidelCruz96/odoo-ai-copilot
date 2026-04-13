import unittest

from agents.agent.intents.planner import build_entities
from agents.agent.intents.semantic_frame import (
    apply_frame_to_plan,
    build_semantic_frame,
    resolve_intent_variant,
)


class TestSemanticFrame(unittest.TestCase):
    def test_build_semantic_frame_for_issued_invoices(self):
        entities = build_entities("que facturas se emitieron esta semana")
        frame = build_semantic_frame(
            "que facturas se emitieron esta semana",
            intent_name="list_facturas_emitidas_periodo",
            entities=entities,
        )

        self.assertEqual(frame.get("model"), "account.move")
        self.assertEqual(frame.get("business_object"), "invoice")
        self.assertEqual(frame.get("action"), "list")
        self.assertEqual(frame.get("filters", {}).get("state"), "posted")
        self.assertEqual(frame.get("filters", {}).get("move_type"), "out_invoice")
        self.assertIsInstance(frame.get("time_range"), dict)

    def test_resolve_intent_variant_count_to_list(self):
        entities = build_entities("muestrame las facturas pendientes")
        frame = build_semantic_frame(
            "muestrame las facturas pendientes",
            intent_name="count_facturas_pendientes",
            entities=entities,
        )
        variant = resolve_intent_variant("count_facturas_pendientes", frame)
        self.assertEqual(variant, "list_facturas_pendientes")

    def test_apply_frame_to_plan_enforces_invoice_filters(self):
        plan = {
            "tool": "query_odoo_search",
            "arguments": {
                "model": "account.move",
                "domain": [],
                "orderby": "",
                "limit": 20,
            },
            "read_back": {
                "tool": "query_odoo_read",
                "fields": ["name"],
            },
        }
        frame = {
            "model": "account.move",
            "action": "list",
            "filters": {
                "move_type": "out_invoice",
                "state": "posted",
                "payment_state": ["not_paid", "partial"],
            },
            "time_range": {"from": "2026-04-01", "to": "2026-04-30"},
            "ordering": {"field": "invoice_date", "direction": "desc"},
            "limit": 20,
        }

        adjusted = apply_frame_to_plan(plan, frame)
        domain = adjusted.get("arguments", {}).get("domain", [])
        self.assertIn(["move_type", "=", "out_invoice"], domain)
        self.assertIn(["state", "=", "posted"], domain)
        self.assertIn(["payment_state", "in", ["not_paid", "partial"]], domain)
        self.assertIn(["invoice_date", ">=", "2026-04-01"], domain)
        self.assertIn(["invoice_date", "<=", "2026-04-30"], domain)


if __name__ == "__main__":
    unittest.main()
