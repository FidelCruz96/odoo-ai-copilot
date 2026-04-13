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


if __name__ == "__main__":
    unittest.main()
