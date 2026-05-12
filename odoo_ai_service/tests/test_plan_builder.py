import unittest

from app.agents.plan_builder import build_plan


class TestPlanBuilder(unittest.TestCase):
    def test_amount_lookup_plan(self):
        plan = build_plan(
            route="erp_data",
            domain="purchase",
            intent="amount_lookup",
            entity={"type": "purchase_order", "code": "PO-I-10-00026", "model": "purchase.order", "lookup_field": "name"},
        )
        self.assertEqual(plan[0]["tool"], "query_odoo_search")
        self.assertEqual(plan[1]["tool"], "query_odoo_read")

    def test_policy_validation_plan(self):
        plan = build_plan(
            route="mixed",
            domain="purchase",
            intent="policy_validation",
            entity={"type": "purchase_order", "model": "purchase.order", "id": 113},
        )
        self.assertEqual(plan[0]["tool"], "query_odoo_read")
        self.assertEqual(plan[1]["tool"], "search_knowledge")

    def test_sale_count_plan(self):
        plan = build_plan(route="erp_data", domain="sale", intent="count", entity=None)
        self.assertEqual(plan[0]["tool"], "query_odoo_count")
        self.assertEqual(plan[0]["args"]["model"], "sale.order")

    def test_count_ignores_active_entity_model(self):
        plan = build_plan(
            route="erp_data",
            domain="sale",
            intent="count",
            entity={"type": "purchase_order", "model": "purchase.order", "id": 113},
        )

        self.assertEqual(plan[0]["args"]["model"], "sale.order")

    def test_ranking_ignores_active_entity_model(self):
        plan = build_plan(
            route="erp_data",
            domain="invoice",
            intent="ranking",
            entity={"type": "purchase_order", "model": "purchase.order", "id": 113},
        )

        self.assertEqual(plan[0]["args"]["model"], "account.move")

    def test_status_lookup_with_code_uses_search_then_read(self):
        plan = build_plan(
            route="erp_data",
            domain="sale",
            intent="status_lookup",
            entity={"type": "sale_order", "code": "DCN 0426-0039", "model": "sale.order", "lookup_field": "name"},
        )

        self.assertEqual([step["tool"] for step in plan], ["query_odoo_search", "query_odoo_read"])
        self.assertEqual(plan[1]["args"]["fields"], ["name", "state"])

    def test_invoice_ranking_plan(self):
        plan = build_plan(route="erp_data", domain="invoice", intent="ranking", entity=None)
        self.assertEqual(plan[0]["tool"], "query_odoo_group")
        self.assertEqual(plan[0]["args"]["model"], "account.move")
        self.assertEqual(plan[0]["args"]["groupby"], ["partner_id"])

    def test_document_sale_ranking_uses_search_and_read(self):
        plan = build_plan(route="erp_data", domain="sale", intent="ranking", entity=None, question="top ventas")

        self.assertEqual([step["tool"] for step in plan], ["query_odoo_search", "query_odoo_read"])
        self.assertEqual(plan[0]["args"]["model"], "sale.order")
        self.assertEqual(plan[0]["args"]["orderby"], "amount_total desc")

    def test_customer_sale_ranking_keeps_groupby(self):
        plan = build_plan(route="erp_data", domain="sale", intent="ranking", entity=None, question="top clientes por ventas")

        self.assertEqual(plan[0]["tool"], "query_odoo_group")
        self.assertEqual(plan[0]["args"]["groupby"], ["partner_id"])

    def test_document_purchase_ranking_uses_search_and_read(self):
        plan = build_plan(route="erp_data", domain="purchase", intent="ranking", entity=None, question="top compras")

        self.assertEqual([step["tool"] for step in plan], ["query_odoo_search", "query_odoo_read"])
        self.assertEqual(plan[0]["args"]["model"], "purchase.order")

    def test_document_invoice_ranking_uses_search_and_read(self):
        plan = build_plan(route="erp_data", domain="invoice", intent="ranking", entity=None, question="top facturas")

        self.assertEqual([step["tool"] for step in plan], ["query_odoo_search", "query_odoo_read"])
        self.assertEqual(plan[0]["args"]["model"], "account.move")

    def test_document_invoice_ranking_accepts_singular_highest_phrase(self):
        plan = build_plan(route="erp_data", domain="invoice", intent="ranking", entity=None, question="facturacion mas alta")

        self.assertEqual([step["tool"] for step in plan], ["query_odoo_search", "query_odoo_read"])
        self.assertEqual(plan[0]["args"]["orderby"], "amount_total desc")

    def test_knowledge_uses_original_question(self):
        plan = build_plan(
            route="knowledge",
            domain="purchase",
            intent="explanation",
            entity=None,
            question="como funciona la politica de aprobacion de compras",
        )

        self.assertIn("como funciona la politica de aprobacion de compras", plan[0]["args"]["query"])
        self.assertIn("politica aprobacion compras", plan[0]["args"]["query"])

    def test_mixed_query_combines_question_and_canonical_terms(self):
        plan = build_plan(
            route="mixed",
            domain="purchase",
            intent="policy_validation",
            entity={"type": "purchase_order", "model": "purchase.order", "id": 113},
            question="cumple po-i-10-00026 segun la politica",
        )

        self.assertIn("cumple po-i-10-00026 segun la politica", plan[1]["args"]["query"])
        self.assertIn("politica aprobacion compras", plan[1]["args"]["query"])


if __name__ == "__main__":
    unittest.main()
