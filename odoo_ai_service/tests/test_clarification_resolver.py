import unittest

from agents.agent.clarification_resolver import detect_clarification_needed, resolve_pending_clarification


class TestClarificationResolver(unittest.TestCase):
    def test_sales_vs_invoices_asks_when_ambiguous(self):
        result = detect_clarification_needed("muéstrame las ventas pendientes", memory={})
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("name"), "sales_vs_invoices_scope")

    def test_sales_vs_invoices_does_not_ask_when_invoice_is_explicit(self):
        result = detect_clarification_needed("muéstrame las facturas pendientes", memory={})
        self.assertIsNone(result)

    def test_sales_vs_invoices_resolution_rewrites_question(self):
        memory = {
            "pending_clarification": {
                "name": "sales_vs_invoices_scope",
                "question": "¿Te refieres a pedidos de venta o a facturas emitidas?",
                "original_question": "muéstrame las ventas pendientes",
            }
        }
        result = resolve_pending_clarification("facturas emitidas", memory)
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("resolved"))
        self.assertIn("facturas emitidas", result.get("rewritten_question", ""))

    def test_count_vs_list_asks_when_action_is_ambiguous(self):
        result = detect_clarification_needed("facturas pendientes este mes", memory={})
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("name"), "count_vs_list_scope")

    def test_count_vs_list_does_not_ask_when_count_is_explicit(self):
        result = detect_clarification_needed("cuántas facturas pendientes hay este mes", memory={})
        self.assertIsNone(result)

    def test_count_vs_list_resolution_to_detail(self):
        memory = {
            "pending_clarification": {
                "name": "count_vs_list_scope",
                "question": "¿Quieres solo el total o quieres ver el detalle?",
                "original_question": "facturas pendientes este mes",
            }
        }
        result = resolve_pending_clarification("detalle", memory)
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("resolved"))
        self.assertIn("detalle", result.get("rewritten_question", ""))

    def test_followup_entity_clarification_resolves_selected_entity(self):
        memory = {
            "pending_clarification": {
                "name": "entity_followup_scope",
                "question": "¿Te refieres a la compra PO-I-10-00015 o a la venta DCN 0426-0056?",
                "original_question": "tiene alguna factura?",
                "options": [
                    {
                        "key": "entity_1",
                        "label": "Compra PO-I-10-00015",
                        "value": "compra PO-I-10-00015",
                        "model": "purchase.order",
                        "id": 53,
                        "display_name": "PO-I-10-00015",
                    },
                    {
                        "key": "entity_2",
                        "label": "Venta DCN 0426-0056",
                        "value": "venta DCN 0426-0056",
                        "model": "sale.order",
                        "id": 111,
                        "display_name": "DCN 0426-0056",
                    },
                ],
            }
        }
        result = resolve_pending_clarification("compra PO-I-10-00015", memory)
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("resolved"))
        self.assertEqual(result.get("rewritten_question"), "tiene alguna factura?")
        self.assertEqual(result.get("selected_entity", {}).get("model"), "purchase.order")
        self.assertEqual(result.get("selected_entity", {}).get("id"), 53)

    def test_followup_entity_clarification_keeps_pending_on_unknown_choice(self):
        memory = {
            "pending_clarification": {
                "name": "entity_followup_scope",
                "question": "¿Te refieres a la compra PO-I-10-00015 o a la venta DCN 0426-0056?",
                "original_question": "tiene alguna factura?",
                "options": [
                    {"key": "entity_1", "label": "Compra PO-I-10-00015", "model": "purchase.order", "id": 53},
                    {"key": "entity_2", "label": "Venta DCN 0426-0056", "model": "sale.order", "id": 111},
                ],
            }
        }
        result = resolve_pending_clarification("no sé", memory)
        self.assertIsInstance(result, dict)
        self.assertFalse(result.get("resolved"))
        self.assertIn("compra", result.get("question", "").lower())

    def test_followup_entity_clarification_selects_exact_sale_code(self):
        memory = {
            "pending_clarification": {
                "name": "entity_followup_scope",
                "question": "¿Te refieres a la venta ID 77 o a la venta DCN 0326-0025?",
                "original_question": "tiene alguna factura?",
                "options": [
                    {
                        "key": "entity_1",
                        "label": "Venta ID 77",
                        "value": "venta ID 77",
                        "model": "sale.order",
                        "id": 77,
                        "display_name": "ID 77",
                    },
                    {
                        "key": "entity_2",
                        "label": "Venta DCN 0326-0025",
                        "value": "venta DCN 0326-0025",
                        "model": "sale.order",
                        "id": 75,
                        "display_name": "DCN 0326-0025",
                    },
                ],
            }
        }
        result = resolve_pending_clarification("venta DCN 0326-0025", memory)
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("resolved"))
        self.assertEqual(result.get("selected_entity", {}).get("id"), 75)

    def test_count_vs_list_no_ask_for_clientes_facturas_vencidas_ranking(self):
        result = detect_clarification_needed("¿Qué clientes tienen más facturas vencidas?", memory={})
        self.assertIsNone(result)

    def test_count_vs_list_no_ask_for_ordenes_pendientes_recepcion(self):
        result = detect_clarification_needed("¿Qué órdenes de compra están pendientes de recepción?", memory={})
        self.assertIsNone(result)

    def test_count_vs_list_no_ask_for_pickings_pendientes_validar_hoy(self):
        result = detect_clarification_needed("¿Qué pickings están pendientes de validar hoy?", memory={})
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
