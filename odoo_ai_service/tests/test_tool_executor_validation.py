import unittest
from unittest.mock import patch

from agents.agent.execution.tool_executor import execute_tool


class TestToolExecutorValidation(unittest.TestCase):
    def test_execute_tool_blocks_invalid_arguments_before_odoo_call(self):
        with patch("agents.agent.execution.tool_executor.query_odoo") as query_odoo:
            result = execute_tool("query_odoo_read", {"model": "sale.order", "fields": ["name"]})

        query_odoo.assert_not_called()
        self.assertEqual(result["error"], "invalid_tool_arguments")

    def test_execute_tool_passes_validated_arguments_to_odoo(self):
        with patch("agents.agent.execution.tool_executor.query_odoo", return_value=[1, 2]) as query_odoo:
            result = execute_tool("query_odoo_search", {"model": "sale.order"})

        self.assertEqual(result, [1, 2])
        query_odoo.assert_called_once_with(
            operation="search",
            model="sale.order",
            domain=[],
            orderby=None,
            limit=20,
        )

    def test_execute_tool_passes_internal_context_to_odoo(self):
        context = {"access_context": {"uid": 2, "db_name": "admin"}}
        with patch("agents.agent.execution.tool_executor.query_odoo", return_value=[11]) as query_odoo:
            result = execute_tool("query_odoo_search", {"model": "purchase.order", "context": context})

        self.assertEqual(result, [11])
        query_odoo.assert_called_once_with(
            operation="search",
            model="purchase.order",
            domain=[],
            orderby=None,
            limit=20,
            context=context,
        )


if __name__ == "__main__":
    unittest.main()
