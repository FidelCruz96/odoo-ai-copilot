import unittest

from app.agents.intent_resolver import resolve_intent


class TestIntentResolver(unittest.TestCase):
    def test_amount_lookup(self):
        self.assertEqual(resolve_intent("cuanto de monto tiene po-i-10-00026", entity={"type": "purchase_order"}), "amount_lookup")
        self.assertEqual(resolve_intent("dame el monto total de la compra"), "amount_lookup")

    def test_count(self):
        self.assertEqual(resolve_intent("cuantas compras hay"), "count")

    def test_ranking_amount_variants(self):
        self.assertEqual(resolve_intent("ventas mas altas", domain="sale"), "ranking")
        self.assertEqual(resolve_intent("compras más altas", domain="purchase"), "ranking")
        self.assertEqual(resolve_intent("facturacion mas alta", domain="invoice"), "ranking")

    def test_status_lookup_has_priority_over_explanation_phrase(self):
        self.assertEqual(
            resolve_intent("en que estado se encuentra la compra p00011", domain="purchase"),
            "status_lookup",
        )

    def test_policy_validation(self):
        self.assertEqual(resolve_intent("debio aprobarse esta compra segun la politica"), "policy_validation")
        self.assertEqual(resolve_intent("po-i-10-00026 requiere aprobacion?", domain="purchase", entity={"type": "purchase_order"}), "policy_validation")
        self.assertEqual(resolve_intent("esta compra entra al flujo de aprobacion?", domain="purchase", entity={"type": "relative_reference"}), "policy_validation")
        self.assertEqual(resolve_intent("segun documentacion esta venta cumple?", domain="sale", entity={"type": "relative_reference"}), "policy_validation")

    def test_documentation_guidance_is_explanation(self):
        self.assertEqual(
            resolve_intent("segun la documentacion como debo aprobar compras", domain="purchase"),
            "explanation",
        )
        self.assertEqual(resolve_intent("como funciona la politica de aprobacion"), "explanation")


if __name__ == "__main__":
    unittest.main()
