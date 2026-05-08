import unittest
from unittest.mock import patch

from tools.odoo_get_tool import get_schema, query_odoo


class TestOdooGetToolSecurity(unittest.TestCase):
    def test_query_odoo_blocks_disallowed_model(self):
        with patch("tools.odoo_get_tool.requests.post") as post:
            result = query_odoo(model="res.users", operation="search", limit=10)

        post.assert_not_called()
        self.assertEqual(result["error"], "model_not_allowed")

    def test_query_odoo_blocks_sensitive_fields(self):
        with patch("tools.odoo_get_tool.requests.post") as post:
            result = query_odoo(
                model="res.partner",
                operation="read",
                ids=[1],
                fields=["name", "api_key"],
            )

        post.assert_not_called()
        self.assertEqual(result["error"], "blocked_field_requested")

    def test_query_odoo_blocks_sensitive_groupby(self):
        with patch("tools.odoo_get_tool.requests.post") as post:
            result = query_odoo(
                model="sale.order",
                operation="read_group",
                fields=["amount_total:sum"],
                groupby=["token"],
                limit=10,
            )

        post.assert_not_called()
        self.assertEqual(result["error"], "blocked_field_requested")

    def test_query_odoo_blocks_limit_above_max(self):
        with patch("tools.odoo_get_tool.requests.post") as post:
            result = query_odoo(model="sale.order", operation="search", limit=1000)

        post.assert_not_called()
        self.assertEqual(result["error"], "invalid_limit")

    def test_get_schema_blocks_disallowed_model(self):
        with patch("tools.odoo_get_tool.requests.post") as post:
            result = get_schema(models=["res.users"])

        post.assert_not_called()
        self.assertEqual(result["error"], "model_not_allowed")

    def test_query_odoo_requires_access_context_before_http(self):
        with patch.dict("tools.odoo_get_tool.os.environ", {"ODOO_AI_REQUIRE_ACCESS_CONTEXT": "true"}):
            with patch("tools.odoo_get_tool.requests.post") as post:
                result = query_odoo(model="sale.order", operation="search", limit=10)

        post.assert_not_called()
        self.assertEqual(result["error"], "access_context_required")

    def test_query_odoo_sends_access_context(self):
        class Response:
            ok = True
            text = "[]"

            def json(self):
                return []

        with patch("tools.odoo_get_tool.requests.post", return_value=Response()) as post:
            result = query_odoo(
                model="sale.order",
                operation="search",
                limit=10,
                context={"request_id": "req-1", "security": {"uid": 2, "company_ids": [1]}},
            )

        self.assertEqual(result, [])
        payload = post.call_args.kwargs["json"]["params"]
        self.assertEqual(payload["access_context"]["uid"], 2)
        self.assertEqual(payload["access_context"]["request_id"], "req-1")


if __name__ == "__main__":
    unittest.main()
