"""Tool collection for TripWeave Agent."""

from app.core.tool import ToolRegistry, get_tool_definition
from app.tools.budget import check_budget_limit, estimate_trip_budget
from app.tools.constraints import check_itinerary_constraints
from app.tools.map import estimate_route, geocode, search_poi
from app.tools.packing import generate_packing_and_outfits
from app.tools.weather import get_weather_forecast
from app.tools.tavily import search_travel_notes


def create_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for func in [
        search_poi,
        geocode,
        estimate_route,
        get_weather_forecast,
        estimate_trip_budget,
        check_budget_limit,
        check_itinerary_constraints,
        generate_packing_and_outfits,
        search_travel_notes,
    ]:
        registry.add(get_tool_definition(func))
    return registry
