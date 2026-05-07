import unittest

from app.agents.domain_resolver import resolve_domain


class TestDomainResolver(unittest.TestCase):
    def test_domain_from_purchase_code(self):
        domain = resolve_domain("po-i-10-00026", entity={"type": "purchase_order"})
        self.assertEqual(domain, "purchase")

    def test_domain_from_text(self):
        self.assertEqual(resolve_domain("ventas del mes"), "sale")
        self.assertEqual(resolve_domain("facturas pendientes"), "invoice")
        self.assertEqual(resolve_domain("segun la politica"), "knowledge")

    def test_domain_from_business_code_entity(self):
        domain = resolve_domain(
            "monto de la venta dcn 0426-0039",
            entity={"type": "business_document_code", "target_domain": "sale"},
        )
        self.assertEqual(domain, "sale")


if __name__ == "__main__":
    unittest.main()
