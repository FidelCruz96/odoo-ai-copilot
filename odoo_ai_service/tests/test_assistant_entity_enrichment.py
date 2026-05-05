import unittest
from unittest.mock import patch
import sys
import types

if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")
    openai_stub.OpenAI = object
    openai_stub.RateLimitError = Exception
    openai_stub.APIError = Exception
    openai_stub.APIConnectionError = Exception
    sys.modules["openai"] = openai_stub

from agents.agent import assistant_agent


class TestAssistantEntityEnrichment(unittest.TestCase):
    def test_query_has_explicit_entity_hint_requires_real_document_code(self):
        self.assertFalse(assistant_agent._query_has_explicit_entity_hint("dime que ventas tienen facturas"))
        self.assertTrue(assistant_agent._query_has_explicit_entity_hint("tiene factura la venta DCN 0426-0060"))

    def test_hydrate_entity_display_name_from_read_when_fallback_id(self):
        entity = {
            "model": "sale.order",
            "id": 77,
            "display_name": "ID 77",
            "fields": {"name": "ID 77"},
        }
        with patch(
            "agents.agent.assistant_agent.execute_tool",
            return_value=[{"id": 77, "name": "DCN 0326-0017"}],
        ) as mocked_exec:
            hydrated = assistant_agent._hydrate_entity_display_name(entity)

        self.assertEqual(hydrated.get("display_name"), "DCN 0326-0017")
        self.assertEqual(hydrated.get("fields", {}).get("name"), "DCN 0326-0017")
        mocked_exec.assert_called_once()

    def test_hydrate_entity_display_name_skips_read_when_name_already_present(self):
        entity = {
            "model": "sale.order",
            "id": 77,
            "display_name": "DCN 0326-0017",
            "fields": {"name": "DCN 0326-0017"},
        }
        with patch("agents.agent.assistant_agent.execute_tool") as mocked_exec:
            hydrated = assistant_agent._hydrate_entity_display_name(entity)

        self.assertEqual(hydrated.get("display_name"), "DCN 0326-0017")
        mocked_exec.assert_not_called()

    def test_normalize_read_fields_with_schema_removes_invalid_and_applies_defaults(self):
        arguments = {
            "model": "sale.order",
            "ids": [10],
            "fields": ["display_name", "ref", "name", "amount_total:sum", "invoice_origin"],
        }
        model_info = {
            "fields": {
                "name": {"type": "char"},
                "partner_id": {"type": "many2one"},
                "date_order": {"type": "datetime"},
                "amount_total": {"type": "monetary"},
                "state": {"type": "selection"},
            }
        }
        result = assistant_agent._normalize_read_fields_with_schema(arguments, model_info)
        self.assertEqual(result.get("fields"), ["name"])

        result2 = assistant_agent._normalize_read_fields_with_schema(
            {"model": "sale.order", "ids": [10], "fields": []},
            model_info,
        )
        self.assertEqual(result2.get("fields"), ["name", "partner_id", "date_order", "amount_total", "state"])

    def test_enforce_invoice_semantics_for_purchase_context(self):
        arguments = {
            "model": "account.move",
            "domain": [
                ["purchase_order_id", "=", 53],
                ["sale_id", "=", 77],
                ["state", "=", "posted"],
            ],
        }
        memory = {
            "primary_entity": {
                "model": "purchase.order",
                "id": 53,
                "display_name": "PO-I-10-00044",
                "fields": {"name": "PO-I-10-00044"},
            }
        }
        model_info = {
            "fields": {
                "invoice_origin": {"type": "char"},
                "move_type": {"type": "selection"},
                "state": {"type": "selection"},
            }
        }
        result = assistant_agent._enforce_invoice_semantics(
            arguments,
            "tiene alguna factura?",
            memory,
            "query_odoo_search",
            model_info,
        )
        domain = result.get("domain") or []
        self.assertIn(["invoice_origin", "=", "PO-I-10-00044"], domain)
        self.assertIn(["move_type", "in", ["in_invoice", "in_refund"]], domain)
        self.assertNotIn(["sale_id", "=", 77], domain)
        self.assertNotIn(["purchase_order_id", "=", 53], domain)

    def test_enforce_invoice_semantics_does_not_force_invoice_origin_for_global_query(self):
        arguments = {
            "model": "account.move",
            "domain": [["state", "=", "posted"]],
        }
        memory = {
            "primary_entity": {
                "model": "sale.order",
                "id": 116,
                "display_name": "DCN 0426-0060",
                "fields": {"name": "DCN 0426-0060"},
            }
        }
        model_info = {
            "fields": {
                "invoice_origin": {"type": "char"},
                "move_type": {"type": "selection"},
                "state": {"type": "selection"},
            }
        }
        result = assistant_agent._enforce_invoice_semantics(
            arguments,
            "dime que ventas tienen facturas",
            memory,
            "query_odoo_search",
            model_info,
        )
        domain = result.get("domain") or []
        self.assertNotIn(["invoice_origin", "=", "DCN 0426-0060"], domain)

    def test_clear_resolved_entity_conflicts_keeps_selected_model_recent(self):
        memory = {
            "last_inferred_entity": {"model": "purchase.order", "id": 53, "display_name": "PO-I-10-00044"},
            "recent_entities": [
                {"model": "sale.order", "id": 77, "display_name": "DCN 0326-0017"},
                {"model": "purchase.order", "id": 53, "display_name": "PO-I-10-00044"},
            ],
            "secondary_entity": {"model": "purchase.order", "id": 53, "display_name": "PO-I-10-00044"},
        }
        selected = {"model": "sale.order", "id": 77, "display_name": "DCN 0326-0017"}
        result = assistant_agent._clear_resolved_entity_conflicts(memory, selected)
        self.assertNotIn("last_inferred_entity", result)
        self.assertTrue(all(r.get("model") == "sale.order" for r in result.get("recent_entities", [])))

    def test_execute_related_followup_related_sales_resolves_purchase_name_from_id_context(self):
        plan = {
            "type": "related_followup",
            "intent": "related_sales",
            "source_model": "purchase.order",
            "source_id": 99,
            "source_display_name": "purchase.order #99",
            "search": {
                "model": "sale.order",
                "domain": [["rt_purchase_order", "=", "purchase.order #99"]],
            },
            "read": {
                "model": "sale.order",
                "fields": ["name", "partner_id", "date_order", "amount_total", "state"],
            },
        }
        metrics = {"tools_used": [], "tool_calls": 0}
        calls = []

        def _fake_exec(tool_name, args):
            calls.append((tool_name, args))
            if tool_name == "query_odoo_read" and args.get("model") == "purchase.order":
                return [{"id": 99, "name": "PO-N-00020"}]
            if tool_name == "query_odoo_search":
                self.assertEqual(args.get("domain"), [["rt_purchase_order", "=", "PO-N-00020"]])
                return [44]
            if tool_name == "query_odoo_read" and args.get("model") == "sale.order":
                return [{"id": 44, "name": "SO044", "partner_id": [1, "ACME"], "date_order": "2026-04-14 10:00:00", "amount_total": 120.0, "state": "sale"}]
            return []

        with patch("agents.agent.assistant_agent.execute_tool", side_effect=_fake_exec):
            answer, error = assistant_agent._execute_related_followup(plan, "que venta relacionada tiene esa compra?", metrics)

        self.assertIsNone(error)
        self.assertIn("Ventas relacionadas con PO-N-00020:", answer)
        self.assertTrue(any(c[0] == "query_odoo_search" for c in calls))


if __name__ == "__main__":
    unittest.main()
