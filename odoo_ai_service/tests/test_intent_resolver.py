import unittest

from app.agents.intent_resolver import resolve_intent


class TestIntentResolver(unittest.TestCase):
    def test_amount_lookup(self):
        self.assertEqual(resolve_intent("cuanto de monto tiene po-i-10-00026", entity={"type": "purchase_order"}), "amount_lookup")
        self.assertEqual(resolve_intent("dame el monto total de la compra"), "amount_lookup")

    def test_count(self):
        self.assertEqual(resolve_intent("cuantas compras hay"), "count")

    def test_policy_validation(self):
        self.assertEqual(resolve_intent("debio aprobarse esta compra segun la politica"), "policy_validation")

    def test_documentation_guidance_is_explanation(self):
        self.assertEqual(
            resolve_intent("segun la documentacion como debo aprobar compras", domain="purchase"),
            "explanation",
        )


if __name__ == "__main__":
    unittest.main()
