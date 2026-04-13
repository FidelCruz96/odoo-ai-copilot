import unittest

from agents.agent.memory_store import get_last_entity, update_last_entity


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


if __name__ == "__main__":
    unittest.main()
