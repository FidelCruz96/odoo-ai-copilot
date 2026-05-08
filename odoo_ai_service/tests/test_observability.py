import json
import logging
import unittest

from app.observability import emit_event


class TestObservability(unittest.TestCase):
    def test_emit_event_redacts_sensitive_values_and_truncates_long_strings(self):
        logger = logging.getLogger("test_observability")
        long_text = "x" * 520

        with self.assertLogs("test_observability", level="INFO") as logs:
            emit_event(logger, "REQUEST_START", token="secret-token", question=long_text)

        raw_payload = logs.output[0].split("OBS_EVENT ", 1)[1]
        payload = json.loads(raw_payload)

        self.assertEqual(payload["event"], "REQUEST_START")
        self.assertEqual(payload["token"], "[REDACTED]")
        self.assertTrue(payload["question"].endswith("...[truncated]"))


if __name__ == "__main__":
    unittest.main()
