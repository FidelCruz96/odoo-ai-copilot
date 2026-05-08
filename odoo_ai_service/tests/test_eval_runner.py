import json
import tempfile
import types
import unittest
from pathlib import Path

from evals.run_eval import evaluate_case, load_jsonl, run_eval, summarize_results


class TestEvalRunner(unittest.TestCase):
    def test_load_jsonl_validates_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cases.jsonl"
            path.write_text('{"id":"case-1","question":"cuantas ventas hay"}\n', encoding="utf-8")

            cases = load_jsonl(path)

        self.assertEqual(cases[0]["id"], "case-1")

    def test_evaluate_case_checks_route_tools_model_and_metrics(self):
        case = {
            "id": "case-1",
            "question": "top clientes por facturacion",
            "expected_route": "erp_data",
            "expected_intent": "ranking",
            "expected_tools": ["query_odoo_group"],
            "expected_model": "account.move",
            "grounded": True,
            "response_faithful": True,
            "max_latency_ms": 1000,
            "answer_contains": ["Deco"],
        }
        response = {
            "answer": "Deco Addict",
            "route_selected": "erp_data",
            "intent_detected": "ranking",
            "tools_used": ["query_odoo_group"],
            "latency_ms": 22.0,
            "grounded": True,
            "response_faithful": True,
            "odoo_evidence": [{"model": "account.move"}],
        }

        result = evaluate_case(case, response)

        self.assertTrue(result["ok"])
        self.assertEqual(result["failures"], [])

    def test_evaluate_case_reports_failures(self):
        case = {
            "id": "case-1",
            "question": "cuantas ventas hay",
            "expected_route": "erp_data",
            "expected_tools": ["query_odoo_count"],
        }
        response = {"route_selected": "fallback", "tools_used": []}

        result = evaluate_case(case, response)

        self.assertFalse(result["ok"])
        self.assertTrue(any("route expected" in item for item in result["failures"]))

    def test_summarize_results_adds_quality_latency_and_tool_breakdown(self):
        results = [
            {
                "id": "ok-1",
                "ok": True,
                "route": "erp_data",
                "intent": "ranking",
                "tools": ["query_odoo_group"],
                "latency_ms": 100.0,
                "tokens_used": 10,
                "failures": [],
            },
            {
                "id": "bad-1",
                "ok": False,
                "route": "fallback",
                "intent": None,
                "tools": [],
                "latency_ms": 300.0,
                "tokens_used": 0,
                "failures": ["route expected='erp_data' actual='fallback'"],
            },
        ]

        summary = summarize_results(results, duration_ms=500.0)

        self.assertEqual(summary["pass_rate"], 50.0)
        self.assertEqual(summary["latency_ms"]["avg"], 200.0)
        self.assertEqual(summary["tokens"]["total"], 10)
        self.assertEqual(summary["tools"]["query_odoo_group"], 1)
        self.assertEqual(summary["failed_case_ids"], ["bad-1"])

    def test_dry_run_report_includes_dataset_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cases.jsonl"
            path.write_text('{"id":"case-1","question":"cuantas ventas hay"}\n', encoding="utf-8")
            args = types.SimpleNamespace(dataset=str(path), dry_run=True)

            report = run_eval(args)

        self.assertTrue(report["ok"])
        self.assertEqual(report["mode"], "dry_run")
        self.assertEqual(report["summary"]["case_ids"], ["case-1"])


if __name__ == "__main__":
    unittest.main()
