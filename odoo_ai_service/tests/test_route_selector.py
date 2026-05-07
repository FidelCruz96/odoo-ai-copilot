import unittest

from app.agents.route_selector import CLARIFICATION, ERP_DATA, KNOWLEDGE, MIXED, select_route


class TestRouteSelector(unittest.TestCase):
    def test_erp_route(self):
        self.assertEqual(select_route("purchase", "amount_lookup", {"type": "purchase_order"}, False), ERP_DATA)

    def test_knowledge_route(self):
        self.assertEqual(select_route("knowledge", "explanation", None, False), KNOWLEDGE)

    def test_knowledge_route_for_business_documentation(self):
        self.assertEqual(select_route("purchase", "explanation", None, False), KNOWLEDGE)

    def test_mixed_route(self):
        self.assertEqual(select_route("purchase", "policy_validation", {"type": "purchase_order"}, False), MIXED)

    def test_clarification_route(self):
        self.assertEqual(select_route("purchase", "policy_validation", {"type": "relative_reference"}, True), CLARIFICATION)


if __name__ == "__main__":
    unittest.main()
