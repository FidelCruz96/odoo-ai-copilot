import unittest

from agents.agent.memory_store import get_last_entity, get_entity_candidates, set_last_ui_entity, update_last_entity


class TestMemoryStore(unittest.TestCase):
    def test_primary_entity_persists_when_secondary_arrives(self):
        memory = {}
        primary = {
            "model": "sale.order",
            "id": 44,
            "display_name": "SO044",
            "fields": {"name": "SO044"},
        }
        secondary = {
            "model": "sale.order.line",
            "id": 441,
            "display_name": "SO044-L1",
            "fields": {"name": "SO044-L1"},
        }

        memory = update_last_entity(memory, primary, source_query="venta principal")
        memory = update_last_entity(memory, secondary, source_query="linea relacionada")

        self.assertEqual(memory.get("primary_entity", {}).get("model"), "sale.order")
        self.assertEqual(memory.get("secondary_entity", {}).get("model"), "sale.order.line")
        self.assertEqual(memory.get("last_entity", {}).get("model"), "sale.order")

    def test_get_last_entity_prefers_primary_entity(self):
        context = {
            "memory": {
                "primary_entity": {
                    "model": "sale.order",
                    "id": 44,
                    "display_name": "SO044",
                    "fields": {},
                },
                "last_entity": {
                    "model": "sale.order.line",
                    "id": 441,
                    "display_name": "SO044-L1",
                    "fields": {},
                },
            }
        }
        result = get_last_entity(context)
        self.assertEqual(result.get("model"), "sale.order")

    def test_get_last_entity_prefers_last_explicit_entity(self):
        context = {
            "memory": {
                "primary_entity": {
                    "model": "sale.order",
                    "id": 44,
                    "display_name": "SO044",
                    "fields": {},
                },
                "last_explicit_entity": {
                    "model": "purchase.order",
                    "id": 53,
                    "display_name": "PO053",
                    "fields": {},
                },
            }
        }
        result = get_last_entity(context)
        self.assertEqual(result.get("model"), "purchase.order")
        self.assertEqual(result.get("id"), 53)

    def test_update_last_entity_explicit_promotes_primary(self):
        memory = {}
        memory = set_last_ui_entity(
            memory,
            {"model": "sale.order", "id": 111, "display_name": "SO111", "fields": {"name": "SO111"}},
            source_query="ui",
        )
        memory = update_last_entity(
            memory,
            {"model": "purchase.order", "id": 53, "display_name": "PO053", "fields": {"name": "PO053"}},
            source_query="consulta explicita",
            source="explicit",
        )

        self.assertEqual(memory.get("primary_entity", {}).get("model"), "purchase.order")
        self.assertEqual(memory.get("last_explicit_entity", {}).get("id"), 53)
        self.assertEqual(memory.get("last_entity", {}).get("id"), 53)

    def test_get_entity_candidates_prioritized_order(self):
        memory = {}
        memory = set_last_ui_entity(
            memory,
            {"model": "sale.order", "id": 111, "display_name": "SO111", "fields": {}},
            source_query="ui",
        )
        memory = update_last_entity(
            memory,
            {"model": "purchase.order", "id": 53, "display_name": "PO053", "fields": {}},
            source_query="explicita",
            source="explicit",
        )
        memory = update_last_entity(
            memory,
            {"model": "purchase.order.line", "id": 390, "display_name": "POL390", "fields": {}},
            source_query="relacionada",
            source="inferred",
        )

        candidates = get_entity_candidates(memory)
        self.assertTrue(candidates)
        self.assertEqual(candidates[0].get("source"), "last_explicit_entity")
        self.assertEqual(candidates[0].get("model"), "purchase.order")


if __name__ == "__main__":
    unittest.main()
