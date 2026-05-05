import unittest

from agents.agent.tool_schemas import validate_tool_arguments


class TestToolSchemas(unittest.TestCase):
    def test_valid_search_arguments_get_defaults(self):
        args, error = validate_tool_arguments("query_odoo_search", {"model": "sale.order"})

        self.assertIsNone(error)
        self.assertEqual(args["model"], "sale.order")
        self.assertEqual(args["domain"], [])
        self.assertEqual(args["limit"], 20)

    def test_read_arguments_reject_missing_ids(self):
        args, error = validate_tool_arguments(
            "query_odoo_read",
            {
                "model": "sale.order",
                "fields": ["name"],
            },
        )

        self.assertIsNone(args)
        self.assertEqual(error["error"], "invalid_tool_arguments")
        self.assertEqual(error["tool"], "query_odoo_read")

    def test_group_arguments_reject_extra_fields(self):
        args, error = validate_tool_arguments(
            "query_odoo_group",
            {
                "model": "sale.order",
                "fields": ["amount_total:sum"],
                "groupby": ["partner_id"],
                "unexpected": True,
            },
        )

        self.assertIsNone(args)
        self.assertEqual(error["error"], "invalid_tool_arguments")


if __name__ == "__main__":
    unittest.main()
