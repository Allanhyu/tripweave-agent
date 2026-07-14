import unittest

from app.core.memory import MemoryManager
from app.core.tool import get_tool_definition, tool
from app.tools import create_default_tool_registry
from app.tools.budget import check_budget_limit, estimate_trip_budget


@tool(description="Test schema generation.")
def sample_tool(city: str, days: int = 2) -> dict:
    return {"city": city, "days": days}


class ToolRegistryTests(unittest.TestCase):
    def test_decorator_builds_json_schema(self):
        definition = get_tool_definition(sample_tool)
        self.assertEqual(definition.name, "sample_tool")
        self.assertEqual(definition.schema["parameters"]["properties"]["city"]["type"], "string")
        self.assertEqual(definition.schema["parameters"]["properties"]["days"]["default"], 2)
        self.assertEqual(definition.schema["parameters"]["required"], ["city"])

    def test_default_registry_contains_active_tools(self):
        names = set(create_default_tool_registry().names())
        self.assertIn("search_poi", names)
        self.assertIn("get_weather_forecast", names)
        self.assertIn("search_travel_notes", names)
        self.assertNotIn("search_xhs_travel_notes", names)


class MemoryManagerTests(unittest.TestCase):
    def test_message_window_discards_oldest_item(self):
        memory = MemoryManager(window_size=2)
        memory.add_message("user", "first")
        memory.add_message("assistant", "second")
        memory.add_message("user", "third")
        self.assertEqual([item.content for item in memory.get_messages()], ["second", "third"])


class BudgetTests(unittest.TestCase):
    def test_budget_uses_days_and_nights(self):
        result = estimate_trip_budget(
            days=3,
            attractions_cost_per_day=50,
            meals_cost_per_day=100,
            hotel_cost_per_night=200,
            transportation_total=80,
            misc_total=20,
        )
        self.assertEqual(result["nights"], 2)
        self.assertEqual(result["total"], 950)

    def test_budget_limit_reports_overrun(self):
        result = check_budget_limit({"total": 1200, "breakdown": {"hotels": 600}}, 1000)
        self.assertTrue(result["over_budget"])
        self.assertEqual(result["remaining"], -200)


if __name__ == "__main__":
    unittest.main()
