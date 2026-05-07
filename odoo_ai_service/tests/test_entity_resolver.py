import unittest

from app.agents.entity_resolver import resolve_entity


class TestEntityResolver(unittest.TestCase):
    def test_detect_purchase_order_code(self):
        entity = resolve_entity("monto de po-i-10-00026")
        self.assertEqual(entity["type"], "purchase_order")
        self.assertEqual(entity["code"], "PO-I-10-00026")
        self.assertEqual(entity["model"], "purchase.order")

    def test_detect_sale_order_code(self):
        entity = resolve_entity("estado de so-2024-0001")
        self.assertEqual(entity["type"], "sale_order")
        self.assertEqual(entity["model"], "sale.order")

    def test_detect_relative_reference(self):
        entity = resolve_entity("debio aprobarse esta compra")
        self.assertEqual(entity["type"], "relative_reference")
        self.assertEqual(entity["target_domain"], "purchase")

    def test_detect_business_code_with_sale_domain_hint(self):
        entity = resolve_entity("monto de la venta dcn 0426-0039")
        self.assertEqual(entity["type"], "business_document_code")
        self.assertEqual(entity["code"], "DCN 0426-0039")
        self.assertEqual(entity["target_domain"], "sale")
        self.assertEqual(entity["model"], "sale.order")


if __name__ == "__main__":
    unittest.main()
