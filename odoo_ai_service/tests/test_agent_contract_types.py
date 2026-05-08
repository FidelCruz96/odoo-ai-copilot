import unittest
from typing import is_typeddict

from app.agents import types


class TestAgentContractTypes(unittest.TestCase):
    def test_core_contracts_are_typeddicts(self):
        for contract in (
            types.Entity,
            types.AccessContext,
            types.AgentContext,
            types.ContextResolution,
            types.ToolArguments,
            types.ToolStep,
            types.ToolExecutionResult,
            types.AgentMetrics,
            types.AgentResponse,
        ):
            self.assertTrue(is_typeddict(contract), contract)

    def test_entity_contract_covers_identity_lookup_and_memory_fields(self):
        annotations = types.Entity.__annotations__

        for field in ("type", "model", "id", "code", "lookup_field", "confidence", "display_name", "fields"):
            self.assertIn(field, annotations)

    def test_access_context_contract_covers_iam_scope(self):
        annotations = types.AccessContext.__annotations__

        for field in ("uid", "company_ids", "allowed_company_ids", "active_company_id", "groups_hash", "request_id"):
            self.assertIn(field, annotations)

    def test_tool_step_requires_tool_and_args(self):
        self.assertEqual(types.ToolStep.__required_keys__, frozenset({"tool", "args"}))


if __name__ == "__main__":
    unittest.main()
