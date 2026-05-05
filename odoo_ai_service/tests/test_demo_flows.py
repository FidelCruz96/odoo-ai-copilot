import unittest
import sys
import types
from unittest.mock import patch

# Stub mínimo para dependencia OpenAI en import del agente.
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


class TestDemoFlows(unittest.TestCase):
    def _context(self, request_id: str):
        return {
            "request_id": request_id,
            "memory": {},
            "client": {},
        }

    def _fake_execute(self, tool_name: str, arguments: dict):
        model = arguments.get("model") if isinstance(arguments, dict) else None

        if tool_name == "query_odoo_group" and model == "sale.order":
            return [
                {"partner_id": [1, "CLIENTE A"], "amount_total": 5000.0},
                {"partner_id": [2, "CLIENTE B"], "amount_total": 4200.0},
                {"partner_id": [3, "CLIENTE C"], "amount_total": 3900.0},
                {"partner_id": [4, "CLIENTE D"], "amount_total": 3500.0},
                {"partner_id": [5, "CLIENTE E"], "amount_total": 3000.0},
            ]

        if tool_name == "query_odoo_group" and model == "account.move":
            return [
                {"partner_id": [10, "CLIENTE V1"], "partner_id_count": 6, "amount_residual": 1200.0},
                {"partner_id": [11, "CLIENTE V2"], "partner_id_count": 4, "amount_residual": 800.0},
            ]

        if tool_name == "query_odoo_search" and model == "purchase.order":
            return [183, 182]

        if tool_name == "query_odoo_search" and model == "sale.order":
            return [501, 499]

        if tool_name == "query_odoo_read" and model == "sale.order":
            return [
                {
                    "id": 501,
                    "name": "SO-000501",
                    "partner_id": [88, "CLIENTE FACTURAR A"],
                    "date_order": "2026-04-15 08:00:00",
                    "amount_total": 1500.0,
                    "state": "sale",
                    "invoice_status": "to invoice",
                },
                {
                    "id": 499,
                    "name": "SO-000499",
                    "partner_id": [77, "CLIENTE FACTURAR B"],
                    "date_order": "2026-04-14 11:15:00",
                    "amount_total": 950.0,
                    "state": "sale",
                    "invoice_status": "to invoice",
                },
            ]

        if tool_name == "query_odoo_read" and model == "purchase.order":
            return [
                {
                    "id": 183,
                    "name": "PO-I-10-00044",
                    "partner_id": [37432, "PROVEEDOR A"],
                    "state": "purchase",
                    "receipt_status": "partial",
                    "date_order": "2026-04-16 09:00:00",
                },
                {
                    "id": 182,
                    "name": "PO-I-10-00043",
                    "partner_id": [37433, "PROVEEDOR B"],
                    "state": "purchase",
                    "receipt_status": "to_receive",
                    "date_order": "2026-04-16 10:00:00",
                },
            ]

        if tool_name == "query_odoo_search" and model == "stock.picking":
            return [91]

        if tool_name == "query_odoo_read" and model == "stock.picking":
            return [
                {
                    "id": 91,
                    "name": "WH/OUT/00091",
                    "partner_id": [200, "CLIENTE X"],
                    "state": "assigned",
                    "scheduled_date": "2026-04-16 11:00:00",
                    "origin": "SO001",
                    "picking_type_id": [5, "Delivery Orders"],
                }
            ]

        if tool_name == "query_odoo_count":
            domain = arguments.get("domain") if isinstance(arguments, dict) else []
            if model == "stock.picking":
                if domain == [["state", "=", "waiting"]]:
                    return 2
                if domain == [["state", "in", ["assigned", "partially_available"]]]:
                    return 5
                if domain == [["state", "=", "done"]]:
                    return 140
            counts = {
                "sale.order": 3,
                "account.move": 12,
                "purchase.order": 4,
                "stock.picking": 7,
            }
            return counts.get(model, 0)

        return []

    def _assert_deterministic(self, result):
        self.assertEqual(result.get("answer_mode"), "deterministic")
        self.assertFalse(result.get("needs_clarification"))
        metadata = result.get("metadata") or {}
        self.assertEqual(metadata.get("route_selected"), "deterministic")

    def test_demo_flows_are_deterministic(self):
        questions = [
            "¿Cuáles son mis 5 clientes con más ventas este mes?",
            "¿Qué clientes tienen más facturas vencidas?",
            "¿Qué órdenes de compra están pendientes de recepción?",
            "¿Qué pickings están pendientes de validar hoy?",
            "Dame un resumen operativo de hoy",
            "Muéstrame los pedidos de venta pendientes de facturar.",
            "¿Cuántos pickings están en espera, disponible y hecho?",
        ]

        with patch.object(agent, "execute_tool", side_effect=self._fake_execute):
            for idx, question in enumerate(questions, start=1):
                result = agent.ask_agent(question, context=self._context(f"demo_{idx}"), history=[])
                self._assert_deterministic(result)


if __name__ == "__main__":
    unittest.main()
