import json
import tempfile
import unittest
from pathlib import Path

from evals.run_eval import evaluate_case, load_jsonl


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


if __name__ == "__main__":
    unittest.main()
