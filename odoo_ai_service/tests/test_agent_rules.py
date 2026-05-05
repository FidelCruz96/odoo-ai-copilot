import json
import os
import tempfile
import unittest

from agents.agent import agent_rules


class TestAgentRules(unittest.TestCase):
    def tearDown(self):
        if "AGENT_RULES_PATH" in os.environ:
            os.environ.pop("AGENT_RULES_PATH")
        agent_rules.get_agent_rules.cache_clear()

    def test_loads_default_json_config(self):
        agent_rules.get_agent_rules.cache_clear()
        rules = agent_rules.get_agent_rules()
        self.assertIn("explicit_doc_regex", rules)
        self.assertIn("guardrail_terms", rules)
        self.assertIn("clarification", rules)

    def test_env_override_path_merges_rules(self):
        payload = {
            "clarification": {
                "followup_confidence_threshold": 0.9,
            },
            "entity_hint_tokens": ["orden de compra"],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            tmp.write(json.dumps(payload))
            tmp_path = tmp.name

        try:
            os.environ["AGENT_RULES_PATH"] = tmp_path
            agent_rules.get_agent_rules.cache_clear()
            threshold = agent_rules.get_followup_clarification_threshold()
            tokens = agent_rules.get_entity_hint_tokens()
            self.assertEqual(threshold, 0.9)
            self.assertEqual(tokens, ["orden de compra"])
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
