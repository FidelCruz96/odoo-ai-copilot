import unittest

from agents.agent.validators.domain_validator import coerce_domain_id_values, normalize_domain_values
from agents.agent.validators.schema_validator import normalize_orderby


class TestDomainValidator(unittest.TestCase):
    def test_coerce_domain_id_values_for_numeric_strings(self):
        domain = [
            ["order_id", "=", "116"],
            ["id", "in", ["1", "2", "x"]],
            ["name", "=", "116"],
            ["partner_id", "!=", "45"],
        ]

        result = coerce_domain_id_values(domain)

        self.assertEqual(result[0], ["order_id", "=", 116])
        self.assertEqual(result[1], ["id", "in", [1, 2, "x"]])
        self.assertEqual(result[2], ["name", "=", "116"])
        self.assertEqual(result[3], ["partner_id", "!=", 45])

    def test_normalize_orderby_accepts_field_agg_format(self):
        self.assertEqual(normalize_orderby("amount_total:sum desc"), "amount_total desc")
        self.assertEqual(normalize_orderby("sum(amount_total) desc"), "amount_total desc")

    def test_normalize_orderby_accepts_agg_alias_suffix(self):
        self.assertEqual(normalize_orderby("amount_total_sum desc"), "amount_total desc")

    def test_normalize_domain_values_coerces_boolean_and_today(self):
        domain = [
            ["date_done", "=", "False"],
            ["scheduled_date", "today"],
        ]

        normalized = normalize_domain_values(domain)

        self.assertEqual(normalized[0], ["date_done", "=", False])
        self.assertEqual(normalized[1][0], "scheduled_date")
        self.assertEqual(normalized[1][1], ">=")
        self.assertEqual(normalized[2][0], "scheduled_date")
        self.assertEqual(normalized[2][1], "<")


if __name__ == "__main__":
    unittest.main()
