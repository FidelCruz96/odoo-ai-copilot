import unittest
from datetime import date
from unittest.mock import patch

from agents.agent.intents import intent_matcher as matcher
from agents.agent.metrics import telemetry
from agents.agent.intents import defaults


class TestMetrics(unittest.TestCase):
    def test_evaluate_metrics_flags(self):
        metrics = {
            "iterations": 3,
            "latency_ms_total": 5000,
            "tokens_input": 4000,
            "tool_calls": 3,
        }

        telemetry.evaluate_metrics(metrics)

        self.assertIn("high_iterations", metrics["warnings"])
        self.assertIn("high_latency", metrics["warnings"])
        self.assertIn("high_tokens", metrics["warnings"])
        self.assertIn("high_tool_calls", metrics["warnings"])
        self.assertFalse(metrics["pass_optimo"])

    def test_evaluate_metrics_allows_expected_tool_calls_on_operational_summary(self):
        metrics = {
            "route_selected": "deterministic",
            "intent_detected": "resumen_operativo_hoy",
            "iterations": 0,
            "latency_ms_total": 300,
            "tokens_input": 0,
            "tool_calls": 4,
        }

        telemetry.evaluate_metrics(metrics)

        self.assertNotIn("high_tool_calls", metrics["warnings"])

    def test_detect_intent(self):
        self.assertEqual(matcher.detect_intent("promedio por cliente"), "avg_group:partner_id")
        self.assertEqual(matcher.detect_intent("cuantos pedidos hay"), "count")
        self.assertEqual(matcher.detect_intent("monto de esos clientes"), "amount_followup")

    def test_evaluate_metrics_quality_warnings(self):
        metrics = {
            "iterations": 1,
            "latency_ms_total": 200,
            "tokens_input": 100,
            "tool_calls": 1,
            "entity_consistent": False,
            "ranking_preserved": False,
            "response_faithful": False,
        }

        telemetry.evaluate_metrics(metrics)

        self.assertIn("entity_inconsistent", metrics["warnings"])
        self.assertIn("ranking_not_preserved", metrics["warnings"])
        self.assertIn("response_not_faithful", metrics["warnings"])
        self.assertFalse(metrics["pass_optimo"])

    def test_update_quality_metrics_from_group_result(self):
        metrics = {}
        arguments = {"orderby": "amount_total desc"}
        result_ok = [
            {"partner_id": [1, "A"], "amount_total": 200},
            {"partner_id": [2, "B"], "amount_total": 150},
            {"partner_id": [3, "C"], "amount_total": 100},
        ]
        telemetry.update_quality_metrics_from_tool_result(metrics, "query_odoo_group", arguments, result_ok)
        self.assertTrue(metrics.get("ranking_preserved"))

        result_bad = [
            {"partner_id": [1, "A"], "amount_total": 200},
            {"partner_id": [2, "B"], "amount_total": 250},
            {"partner_id": [3, "C"], "amount_total": 100},
        ]
        telemetry.update_quality_metrics_from_tool_result(metrics, "query_odoo_group", arguments, result_bad)
        self.assertFalse(metrics.get("ranking_preserved"))

    def test_detect_intent_family(self):
        self.assertEqual(matcher.detect_intent_family("ventas del mes"), "ventas")
        self.assertEqual(matcher.detect_intent_family("compras de la ultima semana"), "compras")
        self.assertEqual(matcher.detect_intent_family("facturas vencidas"), "facturacion")
        self.assertEqual(matcher.detect_intent_family("top clientes"), "clientes")
        self.assertEqual(matcher.detect_intent_family("producto mas vendido"), "productos")
        self.assertEqual(matcher.detect_intent_family("stock disponible"), "inventario")
        self.assertEqual(matcher.detect_intent_family("saludo"), "general")

    def test_detect_catalog_intent(self):
        self.assertEqual(
            matcher.detect_catalog_intent("dime las ultimas ventas que tengan facturas")[0],
            "list_ultimas_ventas_con_factura",
        )
        self.assertEqual(
            matcher.detect_catalog_intent("dime las ultimas compras que tengan facturas")[0],
            "list_ultimas_compras_con_factura",
        )
        self.assertEqual(matcher.detect_catalog_intent("últimos clientes creados")[0], "ultimos_clientes_creados")
        self.assertEqual(matcher.detect_catalog_intent("top vendedor por monto")[0], "top_vendedor_por_monto")
        self.assertEqual(matcher.detect_catalog_intent("top vendedor por pedidos")[0], "top_vendedor_por_pedidos")
        self.assertEqual(matcher.detect_catalog_intent("top cliente por monto")[0], "top_cliente_por_monto")
        self.assertEqual(matcher.detect_catalog_intent("top proveedor por compras")[0], "top_proveedor_por_compras")
        self.assertEqual(matcher.detect_catalog_intent("producto mas comprado")[0], "producto_mas_comprado")
        self.assertEqual(matcher.detect_catalog_intent("total ventas este mes")[0], "ventas_total_periodo")
        self.assertEqual(matcher.detect_catalog_intent("cuántos clientes tengo")[0], "count_clientes")
        self.assertEqual(matcher.detect_catalog_intent("cuántas órdenes de venta hay este mes")[0], "count_ordenes_venta_periodo")
        self.assertEqual(matcher.detect_catalog_intent("cuántas facturas vencidas tengo")[0], "facturas_vencidas_count")
        self.assertEqual(matcher.detect_catalog_intent("qué cliente compró más este mes")[0], "top_cliente_por_monto")
        self.assertEqual(matcher.detect_catalog_intent("qué producto se vendió más este mes")[0], "producto_mas_vendido_por_cantidad")
        self.assertEqual(matcher.detect_catalog_intent("qué producto generó más ventas este mes")[0], "producto_mas_vendido_por_monto")
        self.assertEqual(matcher.detect_catalog_intent("qué proveedor tuvo más compras este año")[0], "top_proveedor_por_compras")
        self.assertEqual(matcher.detect_catalog_intent("qué proveedor me vendió más unidades este año")[0], "top_proveedor_por_unidades")
        self.assertEqual(matcher.detect_catalog_intent("cuántos productos activos hay")[0], "count_productos_activos")
        self.assertEqual(matcher.detect_catalog_intent("qué producto se vendió más")[0], "producto_mas_vendido_por_cantidad")
        self.assertEqual(matcher.detect_catalog_intent("muéstrame las facturas publicadas pero no pagadas")[0], "list_facturas_pendientes")
        self.assertEqual(matcher.detect_catalog_intent("qué facturas se emitieron esta semana")[0], "list_facturas_emitidas_periodo")
        self.assertEqual(matcher.detect_catalog_intent("¿Cuáles son mis 5 clientes con más ventas este mes?")[0], "top_clientes_ventas_mes")
        self.assertEqual(matcher.detect_catalog_intent("¿Qué clientes tienen más facturas vencidas?")[0], "clientes_facturas_vencidas_ranking")
        self.assertEqual(matcher.detect_catalog_intent("¿Qué órdenes de compra están pendientes de recepción?")[0], "ordenes_compra_pendientes_recepcion")
        self.assertEqual(matcher.detect_catalog_intent("Muéstrame los pedidos de venta pendientes de facturar.")[0], "ordenes_venta_pendientes_facturar")
        self.assertEqual(matcher.detect_catalog_intent("¿Qué pickings están pendientes de validar hoy?")[0], "pickings_pendientes_validar_hoy")
        self.assertEqual(matcher.detect_catalog_intent("¿Cuántos pickings están en espera, disponible y hecho?")[0], "count_pickings_por_estado")
        self.assertEqual(matcher.detect_catalog_intent("Dame un resumen operativo de hoy")[0], "resumen_operativo_hoy")

    def test_update_metrics_from_tool_adds_trace(self):
        metrics = {}
        args = {
            "model": "sale.order",
            "domain": [["state", "in", ["sale", "done"]]],
            "fields": ["name"],
            "orderby": "date_order desc",
            "limit": 5,
        }
        telemetry.update_metrics_from_tool(metrics, "query_odoo_search", args)

        trace = metrics.get("tool_trace")
        self.assertIsInstance(trace, list)
        self.assertEqual(trace[0]["tool"], "query_odoo_search")
        self.assertEqual(trace[0]["model"], "sale.order")

    def test_dedupe_domain_nested(self):
        domain = [
            ["state", "in", ["purchase", "done"]],
            ["state", "in", ["purchase", "done"]],
            ["partner_id", "!=", False],
        ]
        result = defaults._dedupe_domain(domain)
        self.assertEqual(len(result), 2)

    def test_detect_period_range_relative(self):
        class FixedDate(date):
            @classmethod
            def today(cls):
                return cls(2026, 4, 10)

        with patch.object(defaults, "date", FixedDate):
            self.assertEqual(
                defaults.detect_period_range("ayer"),
                (date(2026, 4, 9), date(2026, 4, 9)),
            )
            self.assertEqual(
                defaults.detect_period_range("ultima semana"),
                (date(2026, 3, 30), date(2026, 4, 5)),
            )
            self.assertEqual(
                defaults.detect_period_range("ultimo mes"),
                (date(2026, 3, 1), date(2026, 3, 31)),
            )

    def test_apply_query_guardrails_compras_semana_monto(self):
        class FixedDate(date):
            @classmethod
            def today(cls):
                return cls(2026, 4, 10)

        raw_args = {
            "model": "sale.order",
            "domain": [["create_date", ">=", "2026-04-01"]],
            "orderby": "",
        }
        question = "lista las ultimas compras de la ultima semana mayores a 1000"

        with patch.object(defaults, "date", FixedDate):
            guarded = defaults.apply_query_guardrails("query_odoo_search", raw_args, question)

        self.assertEqual(guarded.get("model"), "purchase.order")
        self.assertEqual(guarded.get("orderby"), "date_order desc")
        self.assertIn(["date_order", ">=", "2026-03-30 00:00:00"], guarded.get("domain", []))
        self.assertIn(["date_order", "<", "2026-04-06 00:00:00"], guarded.get("domain", []))
        self.assertIn(["amount_total", ">=", 1000.0], guarded.get("domain", []))
        self.assertIn(["state", "in", ["purchase", "done"]], guarded.get("domain", []))

    def test_apply_query_guardrails_facturas_emitidas_posted(self):
        class FixedDate(date):
            @classmethod
            def today(cls):
                return cls(2026, 4, 10)

        raw_args = {
            "model": "account.move",
            "domain": [],
            "orderby": "",
        }
        question = "muestrame las facturas emitidas esta semana"

        with patch.object(defaults, "date", FixedDate):
            guarded = defaults.apply_query_guardrails("query_odoo_search", raw_args, question)

        self.assertEqual(guarded.get("model"), "account.move")
        self.assertIn(["state", "=", "posted"], guarded.get("domain", []))
        self.assertIn(["move_type", "in", ["out_invoice", "out_refund"]], guarded.get("domain", []))
        self.assertIn(["invoice_date", ">=", "2026-04-06"], guarded.get("domain", []))
        self.assertIn(["invoice_date", "<=", "2026-04-12"], guarded.get("domain", []))

    def test_apply_query_guardrails_ventas_pendientes_prioriza_sale_order(self):
        raw_args = {
            "model": "account.move",
            "domain": [],
            "orderby": "",
        }
        question = "muestrame las ventas pendientes"

        guarded = defaults.apply_query_guardrails("query_odoo_search", raw_args, question)
        self.assertEqual(guarded.get("model"), "sale.order")
        self.assertIn(["state", "in", ["draft", "sent"]], guarded.get("domain", []))

    def test_apply_query_guardrails_ultimas_ventas_con_factura_no_deriva_a_account_move(self):
        raw_args = {
            "model": "account.move",
            "domain": [],
            "orderby": "",
        }
        question = "dime las ultimas ventas que tengan facturas"

        guarded = defaults.apply_query_guardrails("query_odoo_search", raw_args, question)
        domain = guarded.get("domain", [])
        self.assertEqual(guarded.get("model"), "sale.order")
        self.assertIn(["state", "in", ["sale", "done"]], domain)
        self.assertIn(["invoice_status", "!=", "no"], domain)

    def test_apply_query_guardrails_ultimas_compras_con_factura_no_deriva_a_account_move(self):
        raw_args = {
            "model": "account.move",
            "domain": [],
            "orderby": "",
        }
        question = "dime las ultimas compras que tengan facturas"

        guarded = defaults.apply_query_guardrails("query_odoo_search", raw_args, question)
        domain = guarded.get("domain", [])
        self.assertEqual(guarded.get("model"), "purchase.order")
        self.assertIn(["state", "in", ["purchase", "done"]], domain)
        self.assertIn(["invoice_status", "!=", "no"], domain)

    def test_apply_query_guardrails_ventas_tienen_facturas_no_deriva_a_account_move(self):
        raw_args = {
            "model": "account.move",
            "domain": [],
            "orderby": "",
        }
        question = "dime que ventas tienen facturas"

        guarded = defaults.apply_query_guardrails("query_odoo_search", raw_args, question)
        domain = guarded.get("domain", [])
        self.assertEqual(guarded.get("model"), "sale.order")
        self.assertIn(["state", "in", ["sale", "done"]], domain)
        self.assertIn(["invoice_status", "!=", "no"], domain)

    def test_apply_query_guardrails_compras_tienen_facturas_no_deriva_a_account_move(self):
        raw_args = {
            "model": "account.move",
            "domain": [],
            "orderby": "",
        }
        question = "dime que compras tienen facturas"

        guarded = defaults.apply_query_guardrails("query_odoo_search", raw_args, question)
        domain = guarded.get("domain", [])
        self.assertEqual(guarded.get("model"), "purchase.order")
        self.assertIn(["state", "in", ["purchase", "done"]], domain)
        self.assertIn(["invoice_status", "!=", "no"], domain)

    def test_apply_intent_defaults_top_cliente_por_monto_on_sale_order(self):
        raw_args = {
            "model": "sale.order",
            "domain": [["date_order", ">=", "2026-04-01"], ["date_order", "<=", "2026-04-30"]],
            "groupby": ["partner_id"],
            "fields": ["partner_id", "amount_total:sum"],
            "orderby": "amount_total desc",
            "limit": 10,
        }
        result = defaults.apply_intent_defaults("top_cliente_por_monto", raw_args, "top clientes con ventas este mes")
        domain = result.get("domain", [])

        self.assertIn(["partner_id", "!=", False], domain)
        self.assertIn(["partner_id.customer_rank", ">", 0], domain)
        self.assertIn(["partner_id.parent_id", "=", False], domain)
        self.assertIn(["partner_id.active", "=", True], domain)
        self.assertNotIn(["active", "=", True], domain)
        self.assertNotIn(["customer_rank", ">", 0], domain)
        self.assertNotIn(["parent_id", "=", False], domain)


if __name__ == "__main__":
    unittest.main()
