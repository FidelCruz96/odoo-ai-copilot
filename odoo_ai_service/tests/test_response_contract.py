import unittest
import sys
import types

openai_stub = types.ModuleType("openai")


class _OpenAIStubError(Exception):
    pass


openai_stub.RateLimitError = _OpenAIStubError
openai_stub.APIError = _OpenAIStubError
openai_stub.APIConnectionError = _OpenAIStubError
openai_stub.OpenAI = object
sys.modules.setdefault("openai", openai_stub)

from agents.agent.assistant_agent import _map_error_code, _resolve_answer_mode, _build_response_payload


class TestResponseContract(unittest.TestCase):
    def test_map_error_code(self):
        self.assertEqual(_map_error_code("repeated_tool_call"), "ERR_REPEATED_TOOL_CALL")
        self.assertEqual(_map_error_code("odoo_http_500"), "ERR_TOOL_HTTP")
        self.assertEqual(_map_error_code("schema_invalid"), "ERR_INVALID_FIELD")
        self.assertEqual(_map_error_code(None), None)

    def test_resolve_answer_mode(self):
        self.assertEqual(_resolve_answer_mode({"clarification_asked": True}), "clarification_required")
        self.assertEqual(
            _resolve_answer_mode({"clarification_asked": False, "intent_detected": "x", "tokens_input": 0, "tool_calls": 1}),
            "deterministic",
        )
        self.assertEqual(
            _resolve_answer_mode({"clarification_asked": False, "intent_detected": None, "tokens_input": 10, "tool_calls": 1}),
            "tool_guided",
        )
        self.assertEqual(
            _resolve_answer_mode({"clarification_asked": False, "intent_detected": None, "tokens_input": 10, "tool_calls": 0}),
            "fallback_explanatory",
        )

    def test_build_response_payload(self):
        metrics = {
            "request_id": "req_abc123",
            "clarification_asked": False,
            "intent_detected": "top_cliente_por_monto",
            "tokens_input": 0,
            "tool_calls": 1,
            "tools_used": ["query_odoo_group"],
            "tokens_output": 10,
            "latency_ms_total": 200,
            "route_selected": "deterministic",
        }
        ui_payload = {
            "clarification": None,
            "actions": [{"type": "open_model_list", "label": "Abrir ventas"}],
        }
        context = {
            "company": {"id": 1},
            "client": {"active_model": "sale.order", "active_id": 44},
            "lang": "es_PE",
            "tz": "America/Lima",
        }
        payload = _build_response_payload(
            answer="Resultados:\n1. ACME | amount_total: 100.0",
            success=True,
            error_type=None,
            metrics=metrics,
            response_memory={},
            ui_payload=ui_payload,
            context=context,
        )
        self.assertEqual(payload.get("answer_mode"), "deterministic")
        self.assertEqual(payload.get("answer_type"), "table")
        self.assertEqual(payload.get("request_id"), "req_abc123")
        self.assertFalse(payload.get("needs_clarification"))
        self.assertEqual(payload.get("error_code"), None)
        self.assertEqual(payload.get("metadata", {}).get("context_scope", {}).get("company_id"), 1)


if __name__ == "__main__":
    unittest.main()
