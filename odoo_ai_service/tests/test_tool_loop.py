import sys
import types
import unittest
from unittest.mock import patch

openai_stub = types.ModuleType("openai")


class _OpenAIStubError(Exception):
    pass


openai_stub.RateLimitError = _OpenAIStubError
openai_stub.APIError = _OpenAIStubError
openai_stub.APIConnectionError = _OpenAIStubError
openai_stub.OpenAI = object
sys.modules.setdefault("openai", openai_stub)

from agents.agent.tool_loop import ToolLoopCallbacks, run_tool_guided_loop


class _ToolCall:
    id = "call-1"
    function = types.SimpleNamespace(
        name="query_odoo_group",
        arguments='{"model":"sale.order","domain":[],"fields":["amount_total:sum"],"groupby":[]}',
    )


def _callbacks(is_data_question=True):
    memory = {}

    return ToolLoopCallbacks(
        is_data_question=lambda question: is_data_question,
        is_amount_followup=lambda question: False,
        is_count_question=lambda question: False,
        extract_partner_ids_from_domain=lambda domain: [],
        extract_ids_from_domain=lambda domain: [],
        normalize_read_group_args=lambda args, question: args,
        normalize_read_fields_with_schema=lambda args, schema: args,
        enforce_invoice_semantics=lambda args, question, memory, tool_name, model_info: args,
        detect_avg_group_intent=lambda question: None,
        compute_avg_from_group_rows=lambda rows, entity_field, value_field: None,
        extract_entity_from_tool_result=lambda model, result, tool_name, args: None,
        extract_entity_from_search_result=lambda model, result, args: None,
        hydrate_entity_display_name=lambda entity: entity,
        get_response_memory=lambda: memory,
        set_response_memory=lambda next_memory: memory.update(next_memory),
    )


class TestToolLoop(unittest.TestCase):
    def test_data_question_without_tool_call_returns_no_tool_error(self):
        response = types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(tool_calls=None, content="respuesta"))],
            usage=types.SimpleNamespace(prompt_tokens=3, completion_tokens=2),
        )

        def finalize(answer, success, error_type=None):
            return {"answer": answer, "success": success, "error_type": error_type}

        metrics = {"tools_used": [], "tool_calls": 0, "tokens_input": 0, "tokens_output": 0}

        with patch("agents.agent.tool_loop.call_llm", return_value=response):
            result = run_tool_guided_loop(
                question="cuanto vendimos",
                messages=[{"role": "user", "content": "cuanto vendimos"}],
                max_iterations=1,
                metrics=metrics,
                intent_plan=None,
                catalog_intent=None,
                query_has_explicit_entity_hint=False,
                finalize=finalize,
                callbacks=_callbacks(is_data_question=True),
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "no_tool_for_data")
        self.assertEqual(metrics["tokens_input"], 3)
        self.assertEqual(metrics["tokens_output"], 2)

    def test_legacy_tool_loop_passes_context_to_odoo_tools(self):
        tool_response = types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(tool_calls=[_ToolCall()], content=None))],
            usage=types.SimpleNamespace(prompt_tokens=3, completion_tokens=2),
        )
        final_response = types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(tool_calls=None, content="ok"))],
            usage=types.SimpleNamespace(prompt_tokens=4, completion_tokens=1),
        )

        def finalize(answer, success, error_type=None):
            return {"answer": answer, "success": success, "error_type": error_type}

        context = {"access_context": {"uid": 2, "db_name": "admin"}, "request_id": "req-test"}
        metrics = {"tools_used": [], "tool_calls": 0, "tokens_input": 0, "tokens_output": 0}

        with patch("agents.agent.tool_loop.call_llm", side_effect=[tool_response, final_response]):
            with patch("agents.agent.tool_loop.get_model_schema", return_value=None):
                with patch("agents.agent.tool_loop.execute_tool", return_value=[{"amount_total": 100.0}]) as execute_tool:
                    result = run_tool_guided_loop(
                        question="ventas del mes",
                        messages=[{"role": "user", "content": "ventas del mes"}],
                        max_iterations=2,
                        metrics=metrics,
                        intent_plan=None,
                        catalog_intent=None,
                        query_has_explicit_entity_hint=False,
                        context=context,
                        finalize=finalize,
                        callbacks=_callbacks(is_data_question=True),
                    )

        self.assertTrue(result["success"])
        self.assertEqual(execute_tool.call_args.args[1]["context"], context)


if __name__ == "__main__":
    unittest.main()
