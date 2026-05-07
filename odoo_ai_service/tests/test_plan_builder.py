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


if __name__ == "__main__":
    unittest.main()
