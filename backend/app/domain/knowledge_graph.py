"""Build frontend-friendly trip structures and knowledge graph data."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from app.domain.schemas import TripPlanningRequest


GRAPH_CATEGORIES = [
    {"name": "city"},
    {"name": "day"},
    {"name": "attraction"},
    {"name": "restaurant"},
    {"name": "hotel"},
    {"name": "weather"},
    {"name": "budget"},
    {"name": "constraint"},
    {"name": "packing"},
    {"name": "research"},
]

NODE_STYLE = {
    "city": {"symbolSize": 68, "color": "#2563eb"},
    "day": {"symbolSize": 48, "color": "#0891b2"},
    "attraction": {"symbolSize": 38, "color": "#16a34a"},
    "restaurant": {"symbolSize": 32, "color": "#f97316"},
    "hotel": {"symbolSize": 34, "color": "#ca8a04"},
    "weather": {"symbolSize": 34, "color": "#38bdf8"},
    "budget": {"symbolSize": 42, "color": "#dc2626"},
    "constraint": {"symbolSize": 36, "color": "#9333ea"},
    "packing": {"symbolSize": 34, "color": "#0f766e"},
    "research": {"symbolSize": 36, "color": "#e11d48"},
}


def build_structured_plan(
    request: TripPlanningRequest,
    steps: List[dict],
    content: str = "",
) -> Dict[str, Any]:
    """Extract stable UI data from tool observations."""
    attractions = _merge_pois(
        _observation_by_purpose(steps, "research_candidate_attractions"),
        _observation_by_purpose(steps, "attractions"),
        _observation_by_purpose(steps, "supplemental_attractions"),
    )
    restaurants = (_observation_by_purpose(steps, "restaurants") or {}).get("pois") or []
    hotels = (_observation_by_purpose(steps, "hotels") or {}).get("pois") or []
    travel_insights = _observation_by_purpose(steps, "travel_insights") or {}
    weather = _observation_by_tool(steps, "get_weather_forecast") or {}
    budget = _observation_by_tool(steps, "estimate_trip_budget") or {}
    budget_check = _observation_by_tool(steps, "check_budget_limit") or {}
    constraints = _observation_by_tool(steps, "check_itinerary_constraints") or {}
    packing = _observation_by_tool(steps, "generate_packing_and_outfits") or {}

    itinerary_days = (
        (_arguments_by_tool(steps, "check_itinerary_constraints") or {}).get("itinerary_days")
        or _build_days_from_pois(request.days, attractions)
    )
    itinerary_days = _enrich_itinerary_days(
        itinerary_days,
        request=request,
        weather=weather,
        restaurants=restaurants,
        hotels=hotels,
    )

    return {
        "city": request.city,
        "start_date": request.start_date,
        "days_count": request.days,
        "travelers": request.travelers,
        "preferences": request.preferences,
        "pace": request.pace,
        "accommodation": request.accommodation,
        "transportation": request.transportation,
        "itinerary_days": itinerary_days,
        "attractions": attractions,
        "restaurants": restaurants,
        "hotels": hotels,
        "travel_insights": travel_insights,
        "weather": weather,
        "budget": budget,
        "budget_check": budget_check,
        "constraints": constraints,
        "packing": packing,
        "content": content,
    }


def _enrich_itinerary_days(
    itinerary_days: List[Dict[str, Any]],
    request: TripPlanningRequest,
    weather: Dict[str, Any],
    restaurants: List[Dict[str, Any]],
    hotels: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Add the stable day-card fields that the result UI needs."""
    daily_weather = weather.get("daily") or []
    enriched: List[Dict[str, Any]] = []
    for index, raw_day in enumerate(itinerary_days):
        day = dict(raw_day)
        day_number = int(day.get("day") or index + 1)
        attractions_for_day = day.get("attractions") or []
        weather_item = daily_weather[day_number - 1] if day_number - 1 < len(daily_weather) else {}
        lunch = restaurants[(day_number - 1) % len(restaurants)] if restaurants else None
        dinner = restaurants[day_number % len(restaurants)] if restaurants else None
        hotel = hotels[(day_number - 1) % len(hotels)] if hotels else None
        total_minutes = sum(
            int(item.get("visit_minutes") or item.get("visit_duration") or 0)
            + int(item.get("transfer_minutes") or 0)
            for item in attractions_for_day
        )
        names = [str(item.get("name") or "") for item in attractions_for_day if item.get("name")]
        day.update({
            "day": day_number,
            "date": _offset_date(request.start_date, day_number - 1),
            "city": day.get("city") or request.city,
            "summary": " -> ".join(names) if names else "待安排景点",
            "transportation": request.transportation,
            "total_minutes": total_minutes,
            "weather": weather_item,
            "meals": {"lunch": lunch, "dinner": dinner},
            "hotel": hotel,
        })
        enriched.append(day)
    return enriched


def _offset_date(start_date: str, offset: int) -> str:
    try:
        from datetime import date, timedelta

        return (date.fromisoformat(str(start_date)[:10]) + timedelta(days=offset)).isoformat()
    except ValueError:
        return ""


def build_knowledge_graph(structured_plan: Dict[str, Any]) -> Dict[str, Any]:
    """Build ECharts-compatible graph nodes and edges."""
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    seen = set()

    def add_node(node_id: str, name: str, category: str, value: str = "", extra: Optional[Dict[str, Any]] = None) -> None:
        if not node_id or node_id in seen:
            return
        seen.add(node_id)
        style = NODE_STYLE.get(category, {"symbolSize": 30, "color": "#64748b"})
        node = {
            "id": node_id,
            "name": name,
            "category": _category_index(category),
            "symbolSize": style["symbolSize"],
            "itemStyle": {"color": style["color"]},
            "value": value,
        }
        if extra:
            node.update(extra)
        nodes.append(node)

    def add_edge(source: str, target: str, label: str = "") -> None:
        if source and target:
            edges.append({"source": source, "target": target, "label": label})

    city = str(structured_plan.get("city") or "trip")
    city_id = f"city:{city}"
    add_node(city_id, city, "city", str(structured_plan.get("start_date") or ""))
    city_nodes = {city: city_id}
    if structured_plan.get("cities"):
        for segment in structured_plan.get("cities") or []:
            segment_city = str(segment.get("city") or "").strip()
            if not segment_city:
                continue
            segment_id = f"city:{segment_city}"
            add_node(segment_id, segment_city, "city", f"{segment.get('days', 0)} days")
            add_edge(city_id, segment_id, "route")
            city_nodes[segment_city] = segment_id

    weather_daily = (structured_plan.get("weather") or {}).get("daily") or []
    days = structured_plan.get("itinerary_days") or []
    for day in days:
        day_number = int(day.get("day") or day.get("day_index") or 1)
        day_id = f"day:{day_number}"
        add_node(day_id, f"Day {day_number}", "day", "")
        day_city_id = city_nodes.get(str(day.get("city") or ""), city_id)
        add_edge(day_city_id, day_id, "itinerary")

        weather = weather_daily[day_number - 1] if day_number - 1 < len(weather_daily) else {}
        if weather:
            weather_id = f"weather:{day_number}"
            weather_name = _weather_name(weather)
            add_node(weather_id, weather_name, "weather", str(weather.get("date") or ""))
            add_edge(day_id, weather_id, "weather")

        previous_attr_id = ""
        for index, attraction in enumerate(day.get("attractions") or []):
            name = str(attraction.get("name") or f"Attraction {index + 1}")
            attr_id = f"attr:{day_number}:{index}:{name}"
            value = " | ".join(_clean_parts([
                attraction.get("address"),
                _minutes_text(attraction.get("visit_minutes") or attraction.get("visit_duration")),
                _minutes_text(attraction.get("transfer_minutes"), prefix="transfer "),
            ]))
            add_node(attr_id, name, "attraction", value, {
                "node_type": "attraction",
                "day": day_number,
                "order": index + 1,
                "address": attraction.get("address"),
                "location": attraction.get("location"),
                "research_source": bool(attraction.get("research_source")),
                "research_candidate_name": attraction.get("research_candidate_name"),
                "poi_key": _poi_key(attraction),
            })
            add_edge(day_id, attr_id, "visit")
            if previous_attr_id:
                add_edge(previous_attr_id, attr_id, "next")
            previous_attr_id = attr_id

    for index, poi in enumerate((structured_plan.get("restaurants") or [])[:6]):
        name = str(poi.get("name") or f"Restaurant {index + 1}")
        node_id = f"restaurant:{index}:{name}"
        add_node(node_id, name, "restaurant", str(poi.get("address") or ""))
        add_edge(city_id, node_id, "food")

    for index, poi in enumerate((structured_plan.get("hotels") or [])[:4]):
        name = str(poi.get("name") or f"Hotel {index + 1}")
        node_id = f"hotel:{index}:{name}"
        add_node(node_id, name, "hotel", str(poi.get("address") or ""))
        add_edge(city_id, node_id, "stay")

    budget = structured_plan.get("budget") or {}
    if budget:
        budget_id = "budget:total"
        add_node(budget_id, f"Budget {budget.get('total', 'unknown')}", "budget", "")
        add_edge(city_id, budget_id, "budget")
        breakdown = budget.get("breakdown") or {}
        for key, value in breakdown.items():
            if value is None:
                continue
            item_id = f"budget:{key}"
            add_node(item_id, f"{key}: {value}", "budget", "")
            add_edge(budget_id, item_id, key)

    constraints = structured_plan.get("constraints") or {}
    if constraints:
        constraint_id = "constraint:summary"
        status = "conflict" if constraints.get("has_conflicts") else "ok"
        add_node(constraint_id, f"Constraints: {status}", "constraint", "")
        add_edge(city_id, constraint_id, "check")

    packing = structured_plan.get("packing") or {}
    if packing.get("ok"):
        packing_id = "packing:checklist"
        add_node(packing_id, "Packing checklist", "packing", "")
        add_edge(city_id, packing_id, "prepare")

    research = structured_plan.get("travel_insights") or {}
    if research:
        research_id = "research:insights"
        research_name = "Travel research" if research.get("ok") else "Research unavailable"
        add_node(research_id, research_name, "research", research.get("error") or "")
        add_edge(city_id, research_id, "travel notes")
        merged = research.get("merged_insights") or {}
        for key, label in [
            ("candidate_attractions", "candidate"),
            ("pitfalls", "pitfall"),
            ("reservation_tips", "reservation"),
        ]:
            for index, value in enumerate((merged.get(key) or [])[:5]):
                node_id = f"research:{key}:{index}"
                add_node(node_id, str(value), "research", label)
                add_edge(research_id, node_id, label)

    return {
        "nodes": nodes,
        "edges": edges,
        "categories": GRAPH_CATEGORIES,
    }


def _observation_by_tool(steps: List[dict], tool_name: str) -> Optional[Any]:
    for step in steps:
        if step.get("tool_name") == tool_name:
            return step.get("observation")
    return None


def _arguments_by_tool(steps: List[dict], tool_name: str) -> Optional[Any]:
    for step in steps:
        if step.get("tool_name") == tool_name:
            return step.get("arguments")
    return None


def _observation_by_purpose(steps: List[dict], purpose: str) -> Optional[dict]:
    for step in steps:
        metadata = step.get("metadata") or {}
        if metadata.get("purpose") == purpose:
            return step.get("observation")
    return None


def _merge_pois(*observations: Optional[dict]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    seen = set()
    for observation in observations:
        for poi in (observation or {}).get("pois") or []:
            key = (poi.get("id"), poi.get("name"), poi.get("address"))
            if key in seen:
                continue
            seen.add(key)
            result.append(poi)
    return result


def _poi_key(poi: Dict[str, Any]) -> str:
    location = poi.get("location") or {}
    return "|".join([
        _normalize_key(poi.get("name")),
        _normalize_key(poi.get("address")),
        _normalize_key(location.get("longitude")),
        _normalize_key(location.get("latitude")),
    ])


def _normalize_key(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "")


def _build_days_from_pois(days_count: int, pois: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    days = []
    for day_index in range(max(1, days_count)):
        start = day_index * 2
        days.append({
            "day": day_index + 1,
            "attractions": pois[start:start + 2],
        })
    return days


def _category_index(category: str) -> int:
    for index, item in enumerate(GRAPH_CATEGORIES):
        if item["name"] == category:
            return index
    return 0


def _weather_name(weather: Dict[str, Any]) -> str:
    desc = weather.get("day_weather") or weather.get("weather") or "Weather"
    temp_min = weather.get("temp_min")
    temp_max = weather.get("temp_max")
    if temp_min is None and temp_max is None:
        return str(desc)
    return f"{desc} {temp_min}-{temp_max}C"


def _minutes_text(value: Any, prefix: str = "") -> str:
    if value is None or value == "":
        return ""
    return f"{prefix}{value} min"


def _clean_parts(parts: Iterable[Any]) -> List[str]:
    return [str(part) for part in parts if part not in (None, "")]
