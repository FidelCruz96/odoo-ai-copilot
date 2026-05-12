import unittest
import types
import sys
from unittest.mock import patch

# Stub mínimo para evitar dependencia externa en tests unitarios.
if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")

    class DummyOpenAI:
        def __init__(self, *args, **kwargs):
            pass

    openai_stub.OpenAI = DummyOpenAI
    openai_stub.RateLimitError = Exception
    openai_stub.APIError = Exception
    openai_stub.APIConnectionError = Exception
    sys.modules["openai"] = openai_stub

from agents.agent import assistant_agent as agent


class TestDeterministicRender(unittest.TestCase):
    def _metrics(self):
        return {"tool_calls": 0, "tools_used": []}

    def test_top_group_render_preserves_order(self):
        plan = {
            "tool": "query_odoo_group",
            "arguments": {
                "model": "sale.order",
                "domain": [],
                "fields": ["partner_id", "amount_total:sum"],
                "groupby": ["partner_id"],
                "orderby": "amount_total desc",
                "limit": 3,
            },
        }

        tool_rows = [
            {"partner_id": [10, "CLIENTE Z"], "amount_total": 300.0},
            {"partner_id": [8, "CLIENTE A"], "amount_total": 250.0},
            {"partner_id": [9, "CLIENTE B"], "amount_total": 200.0},
        ]

        with patch.object(agent, "execute_tool", return_value=tool_rows):
            answer, _memory = agent._execute_deterministic_plan(
                "top_cliente_por_monto",
                plan,
                "top cliente por monto",
                self._metrics(),
                {},
            )

        self.assertIn("Resultados:", answer)
        self.assertIn("1. CLIENTE Z | monto: 300.0", answer)
        self.assertIn("2. CLIENTE A | monto: 250.0", answer)
        self.assertIn("3. CLIENTE B | monto: 200.0", answer)

    def test_list_facturas_render_is_deterministic(self):
        plan = {
            "tool": "query_odoo_search",
            "arguments": {
                "model": "account.move",
                "domain": [
                    ["move_type", "=", "out_invoice"],
                    ["state", "=", "posted"],
                    ["payment_state", "in", ["not_paid", "partial"]],
                ],
                "orderby": "invoice_date desc",
                "limit": 2,
            },
            "read_back": {
                "tool": "query_odoo_read",
                "fields": ["name", "partner_id", "invoice_date", "amount_total", "payment_state", "state", "move_type"],
            },
        }

        with patch.object(
            agent,
            "execute_tool",
            side_effect=[
                [12, 11],
                [
                    {
                        "id": 12,
                        "name": "F001-00012",
                        "partner_id": [3, "Cliente 3"],
                        "invoice_date": "2026-04-12",
                        "amount_total": 1200.0,
                        "payment_state": "not_paid",
                        "state": "posted",
                        "move_type": "out_invoice",
                    },
                    {
                        "id": 11,
                        "name": "F001-00011",
                        "partner_id": [2, "Cliente 2"],
                        "invoice_date": "2026-04-11",
                        "amount_total": 900.0,
                        "payment_state": "partial",
                        "state": "posted",
                        "move_type": "out_invoice",
                    },
                ],
            ],
        ):
            answer, _memory = agent._execute_deterministic_plan(
                "list_facturas_pendientes",
                plan,
                "muéstrame las facturas pendientes",
                self._metrics(),
                {},
            )

        self.assertIn("Facturas pendientes:", answer)
        self.assertIn("1. F001-00012 | Cliente: Cliente 3 | Fecha: 2026-04-12", answer)
        self.assertIn("2. F001-00011 | Cliente: Cliente 2 | Fecha: 2026-04-11", answer)

    def test_top_sales_render_individual_orders(self):
        plan = {
            "tool": "query_odoo_search",
            "arguments": {
                "model": "sale.order",
                "domain": [["state", "in", ["sale", "done"]]],
                "orderby": "amount_total desc",
                "limit": 2,
            },
            "read_back": {
                "tool": "query_odoo_read",
                "fields": ["name", "partner_id", "date_order", "amount_total", "state"],
            },
        }

        with patch.object(
            agent,
            "execute_tool",
            side_effect=[
                [44, 45],
                [
                    {"id": 44, "name": "SO044", "partner_id": [10, "Cliente A"], "date_order": "2026-05-01", "amount_total": 9000.0, "state": "sale"},
                    {"id": 45, "name": "SO045", "partner_id": [11, "Cliente B"], "date_order": "2026-05-02", "amount_total": 8000.0, "state": "sale"},
                ],
            ],
        ):
            answer, _memory = agent._execute_deterministic_plan(
                "top_ventas_por_monto",
                plan,
                "top ventas",
                self._metrics(),
                {},
            )

        self.assertIn("Órdenes de venta encontradas:", answer)
        self.assertIn("1. SO044 | Cliente: Cliente A", answer)
        self.assertIn("Monto: 9000.0", answer)

    def test_top_purchases_render_individual_orders(self):
        plan = {
            "tool": "query_odoo_search",
            "arguments": {
                "model": "purchase.order",
                "domain": [["state", "in", ["purchase", "done"]]],
                "orderby": "amount_total desc",
                "limit": 2,
            },
            "read_back": {
                "tool": "query_odoo_read",
                "fields": ["name", "partner_id", "date_order", "amount_total", "state"],
            },
        }

        with patch.object(
            agent,
            "execute_tool",
            side_effect=[
                [31],
                [{"id": 31, "name": "PO031"}],
                [{"id": 31, "name": "PO031", "partner_id": [20, "Proveedor A"], "date_order": "2026-05-03", "amount_total": 7000.0, "state": "purchase"}],
            ],
        ):
            answer, _memory = agent._execute_deterministic_plan(
                "top_compras_por_monto",
                plan,
                "top compras",
                self._metrics(),
                {},
            )

        self.assertIn("Órdenes de compra encontradas:", answer)
        self.assertIn("1. PO031 | Proveedor: Proveedor A", answer)

    def test_top_invoices_render_individual_documents(self):
        plan = {
            "tool": "query_odoo_search",
            "arguments": {
                "model": "account.move",
                "domain": [["move_type", "=", "out_invoice"], ["state", "=", "posted"]],
                "orderby": "amount_total desc",
                "limit": 2,
            },
            "read_back": {
                "tool": "query_odoo_read",
                "fields": ["name", "partner_id", "invoice_date", "amount_total", "payment_state", "state", "move_type"],
            },
        }

        with patch.object(
            agent,
            "execute_tool",
            side_effect=[
                [12],
                [{"id": 12, "name": "INV/2026/00012"}],
                [{"id": 12, "name": "INV/2026/00012", "partner_id": [30, "Cliente C"], "invoice_date": "2026-05-04", "amount_total": 6000.0, "state": "posted"}],
            ],
        ):
            answer, _memory = agent._execute_deterministic_plan(
                "top_facturas_por_monto",
                plan,
                "top facturas",
                self._metrics(),
                {},
            )

        self.assertIn("Documentos encontrados:", answer)
        self.assertIn("1. INV/2026/00012 | Contacto: Cliente C", answer)

    def test_product_qty_group_uses_business_metric_not_auto_count(self):
        plan = {
            "tool": "query_odoo_group",
            "arguments": {
                "model": "sale.order.line",
                "domain": [["order_id.date_order", ">=", "2026-01-01"], ["order_id.date_order", "<=", "2026-12-31"]],
                "fields": ["product_id", "product_uom_qty:sum"],
                "groupby": ["product_id"],
                "orderby": "product_uom_qty desc",
                "limit": 3,
            },
        }

        tool_rows = [
            {"product_id": [660, "PROD A"], "product_id_count": 5, "product_uom_qty": 30500.0},
            {"product_id": [999, "PROD B"], "product_id_count": 1, "product_uom_qty": 20000.0},
            {"product_id": [777, "PROD C"], "product_id_count": 6, "product_uom_qty": 18000.0},
        ]

        with patch.object(agent, "execute_tool", return_value=tool_rows):
            answer, _memory = agent._execute_deterministic_plan(
                "producto_mas_vendido_por_cantidad",
                plan,
                "que productos fueron los mas vendidos este año",
                self._metrics(),
                {},
            )

        self.assertIn("1. PROD A | cantidad: 30500.0", answer)
        self.assertIn("2. PROD B | cantidad: 20000.0", answer)
        self.assertNotIn("product_id_count", answer)

    def test_clientes_facturas_vencidas_ranking_render(self):
        plan = {
            "tool": "query_odoo_group",
            "arguments": {
                "model": "account.move",
                "domain": [
                    ["move_type", "=", "out_invoice"],
                    ["state", "=", "posted"],
                    ["payment_state", "in", ["not_paid", "partial"]],
                    ["invoice_date_due", "<", "2026-04-16"],
                ],
                "fields": ["partner_id", "amount_residual:sum"],
                "groupby": ["partner_id"],
                "orderby": "__count desc",
                "limit": 5,
            },
        }

        tool_rows = [
            {"partner_id": [10, "CLIENTE A"], "partner_id_count": 6, "amount_residual": 1200.0},
            {"partner_id": [11, "CLIENTE B"], "partner_id_count": 4, "amount_residual": 600.0},
        ]

        with patch.object(agent, "execute_tool", return_value=tool_rows):
            answer, _memory = agent._execute_deterministic_plan(
                "clientes_facturas_vencidas_ranking",
                plan,
                "que clientes tienen mas facturas vencidas",
                self._metrics(),
                {},
            )

        self.assertIn("Clientes con más facturas vencidas:", answer)
        self.assertIn("1. CLIENTE A | facturas vencidas: 6 | saldo pendiente: 1200.0", answer)
        self.assertIn("2. CLIENTE B | facturas vencidas: 4 | saldo pendiente: 600.0", answer)

    def test_resumen_operativo_hoy_deterministic(self):
        plan = {
            "tool": "summary_operativo_hoy",
            "arguments": {
                "today": "2026-04-16",
                "today_start": "2026-04-16 00:00:00",
                "tomorrow_start": "2026-04-17 00:00:00",
            },
        }

        with patch.object(agent, "execute_tool", side_effect=[3, 12, 4, 7]):
            answer, _memory = agent._execute_deterministic_plan(
                "resumen_operativo_hoy",
                plan,
                "dame un resumen operativo de hoy",
                self._metrics(),
                {},
            )

        self.assertIn("Resumen operativo de hoy (2026-04-16):", answer)
        self.assertIn("Ventas confirmadas hoy: 3", answer)
        self.assertIn("Facturas pendientes de cobro: 12", answer)
        self.assertIn("Órdenes de compra por recibir: 4", answer)
        self.assertIn("Pickings pendientes de validar: 7", answer)

    def test_count_pickings_por_estado_deterministic(self):
        plan = {
            "tool": "summary_pickings_por_estado",
            "arguments": {},
        }

        with patch.object(agent, "execute_tool", side_effect=[2, 5, 140]):
            answer, _memory = agent._execute_deterministic_plan(
                "count_pickings_por_estado",
                plan,
                "cuantos pickings estan en espera disponible y hecho",
                self._metrics(),
                {},
            )

        self.assertIn("Conteo de pickings por estado:", answer)
        self.assertIn("En espera: 2", answer)
        self.assertIn("Disponible: 5", answer)
        self.assertIn("Hecho: 140", answer)

    def test_purchase_read_render_uses_proveedor_label(self):
        rows = [
            {
                "id": 10,
                "name": "PO-10",
                "partner_id": [3, "Proveedor A"],
                "date_order": "2026-04-16 10:00:00",
                "amount_total": 500.0,
                "state": "purchase",
            }
        ]

        answer = agent._format_deterministic_read_answer("ordenes_compra_pendientes_recepcion", "purchase.order", rows)
        self.assertIn("Órdenes de compra encontradas:", answer)
        self.assertIn("Proveedor: Proveedor A", answer)


if __name__ == "__main__":
    unittest.main()
