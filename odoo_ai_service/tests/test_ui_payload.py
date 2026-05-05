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

from agents.agent.assistant_agent import _build_ui_payload


class TestUiPayload(unittest.TestCase):
    def test_ui_payload_clarification_options(self):
        metrics = {
            "clarification_asked": True,
            "followup_resolved": False,
            "intent_detected": None,
            "tokens_input": 0,
            "tool_calls": 0,
            "grounded": False,
            "semantic_model": None,
            "model_used": None,
        }
        memory = {
            "pending_clarification": {
                "name": "count_vs_list_scope",
                "original_question": "facturas pendientes este mes",
            }
        }

        ui = _build_ui_payload(metrics, memory, success=True)

        self.assertEqual(ui.get("mode"), "clarification")
        self.assertIsInstance(ui.get("clarification"), dict)
        options = ui["clarification"].get("options") or []
        option_labels = {item.get("label") for item in options}
        self.assertIn("Solo total", option_labels)
        self.assertIn("Detalle", option_labels)

    def test_ui_payload_context_and_actions(self):
        metrics = {
            "clarification_asked": False,
            "followup_resolved": False,
            "intent_detected": "list_stock_negativo",
            "tokens_input": 0,
            "tool_calls": 1,
            "grounded": True,
            "semantic_model": "product.product",
            "model_used": "product.product",
        }
        memory = {
            "primary_entity": {
                "model": "product.product",
                "id": 976,
                "display_name": "SILICATO SODIO NEUTRO NACIONAL",
                "fields": {
                    "partner_id": [15, "BOKRA E.I.R.L."],
                },
            }
        }

        ui = _build_ui_payload(metrics, memory, success=True)

        self.assertEqual(ui.get("mode"), "deterministic")
        self.assertIn("SILICATO SODIO NEUTRO NACIONAL", ui.get("context", {}).get("active", ""))
        action_keys = {item.get("key") for item in (ui.get("actions") or [])}
        self.assertIn("open_products", action_keys)
        self.assertIn("open_active_record", action_keys)
        self.assertIn("export_csv", action_keys)

        actions_by_key = {item.get("key"): item for item in (ui.get("actions") or [])}
        self.assertEqual(actions_by_key["open_products"].get("type"), "open_model_list")
        self.assertEqual(actions_by_key["open_products"].get("model"), "product.product")
        self.assertEqual(actions_by_key["open_active_record"].get("type"), "open_record")


if __name__ == "__main__":
    unittest.main()
