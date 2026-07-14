"""Multi-city orchestration built on top of the single-city planner."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import Any, Callable, Dict, List

from app.domain.hybrid_planner import HybridTripPlanner
from app.domain.knowledge_graph import build_knowledge_graph, build_structured_plan
from app.domain.schemas import TripPlanningRequest


def execute_trip_plan(request: TripPlanningRequest, on_step: Callable[[dict], None] | None = None) -> Dict[str, Any]:
    """Run either the existing single-city planner or a merged multi-city plan."""
    segments = _normalize_segments(request)
    if len(segments) <= 1:
        result = HybridTripPlanner().plan(request, on_step=on_step)
        structured = build_structured_plan(request, result.raw_steps, result.content)
        return {
            "content": result.content,
            "step_count": result.step_count,
            "raw_steps": result.raw_steps,
            "warning": result.warning,
            "structured_plan": structured,
            "knowledge_graph": build_knowledge_graph(structured),
        }

    return _execute_multi_city(request, segments, on_step)


def _execute_multi_city(
    request: TripPlanningRequest,
    segments: List[Dict[str, Any]],
    on_step: Callable[[dict], None] | None,
) -> Dict[str, Any]:
    plans: List[Dict[str, Any]] = []
    raw_steps: List[dict] = []
    warnings: List[str] = []
    day_offset = 0

    for segment in segments:
        city = segment["city"]
        days = segment["days"]
        sub_request = replace(
            request,
            city=city,
            start_date=_offset_date(request.start_date, day_offset),
            days=days,
            cities=[],
        )

        def emit_city_step(step: dict, city_name: str = city) -> None:
            tagged = dict(step)
            tagged["city"] = city_name
            tagged["metadata"] = {**(step.get("metadata") or {}), "city": city_name}
            if on_step:
                on_step(tagged)

        result = HybridTripPlanner().plan(sub_request, on_step=emit_city_step)
        structured = build_structured_plan(sub_request, result.raw_steps, result.content)
        structured["city"] = city
        structured["day_offset"] = day_offset
        plans.append(structured)
        raw_steps.extend([{**step, "city": city} for step in result.raw_steps])
        if result.warning:
            warnings.append(f"{city}: {result.warning}")
        day_offset += days

    merged = _merge_plans(request, segments, plans)
    content = "\n\n".join(
        f"## {plan.get('city')}\n{plan.get('content') or ''}" for plan in plans
    )
    return {
        "content": content,
        "step_count": len(raw_steps),
        "raw_steps": raw_steps,
        "warning": "; ".join(warnings) if warnings else None,
        "structured_plan": merged,
        "knowledge_graph": build_knowledge_graph(merged),
    }


def _normalize_segments(request: TripPlanningRequest) -> List[Dict[str, Any]]:
    raw_segments = request.cities or [{"city": request.city, "days": request.days}]
    segments: List[Dict[str, Any]] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        city = str(item.get("city") or "").strip()
        try:
            days = max(1, min(int(item.get("days") or 1), 10))
        except (TypeError, ValueError):
            days = 1
        if city:
            segments.append({"city": city, "days": days})
    return segments or [{"city": request.city, "days": request.days}]


def _merge_plans(request: TripPlanningRequest, segments: List[Dict[str, Any]], plans: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_days = sum(segment["days"] for segment in segments)
    itinerary_days: List[dict] = []
    attractions: List[dict] = []
    restaurants: List[dict] = []
    hotels: List[dict] = []
    weather_daily: List[dict] = []
    weather_available_days = 0
    packing_days: List[dict] = []
    all_conflicts: List[dict] = []
    suggestions: List[str] = []
    notes: List[dict] = []
    merged_insights = {"candidate_attractions": [], "pitfalls": [], "reservation_tips": []}
    budget_breakdown = {"attractions": 0, "meals": 0, "hotels": 0, "transportation": 0, "misc": 0}
    has_conflicts = False
    day_offset = 0

    for segment, plan in zip(segments, plans):
        city = segment["city"]
        for day in plan.get("itinerary_days") or []:
            copied_day = dict(day)
            copied_day["day"] = int(day.get("day") or 1) + day_offset
            copied_day["city"] = city
            itinerary_days.append(copied_day)
        for collection_name, target in [("attractions", attractions), ("restaurants", restaurants), ("hotels", hotels)]:
            for item in plan.get(collection_name) or []:
                target.append({**item, "city": city})

        weather_result = plan.get("weather") or {}
        daily_weather = weather_result.get("daily") or []
        daily_by_date = {
            str(item.get("date")): item
            for item in daily_weather
            if isinstance(item, dict) and item.get("date")
        }
        for local_day in range(segment["days"]):
            expected_date = _offset_date(request.start_date, day_offset + local_day)
            weather_item = daily_by_date.get(expected_date)
            if weather_item:
                weather_daily.append({**weather_item, "city": city, "day": day_offset + local_day + 1})
                weather_available_days += 1
            else:
                weather_daily.append({
                    "city": city,
                    "day": day_offset + local_day + 1,
                    "date": expected_date,
                    "unavailable": True,
                    "error": weather_result.get("error") or "该城市当天暂无可用天气预报",
                })
        daily_packing = (plan.get("packing") or {}).get("onion_layering_calendar") or []
        packing_days.extend([{**item, "day": int(item.get("day") or 1) + day_offset, "city": city} for item in daily_packing])

        constraints = plan.get("constraints") or {}
        has_conflicts = has_conflicts or bool(constraints.get("has_conflicts"))
        for conflict in constraints.get("conflicts") or []:
            copied_conflict = dict(conflict)
            if isinstance(copied_conflict.get("day"), int):
                copied_conflict["day"] += day_offset
            copied_conflict["city"] = city
            all_conflicts.append(copied_conflict)
        suggestions.extend([f"{city}: {item}" for item in constraints.get("suggestions") or []])

        research = plan.get("travel_insights") or {}
        notes.extend(research.get("notes") or [])
        for key in merged_insights:
            merged_insights[key].extend((research.get("merged_insights") or {}).get(key) or [])

        breakdown = (plan.get("budget") or {}).get("breakdown") or {}
        for key in budget_breakdown:
            budget_breakdown[key] += float(breakdown.get(key) or 0)
        day_offset += segment["days"]

        for key in merged_insights:
            merged_insights[key] = list(dict.fromkeys(merged_insights[key]))[:20]

    if len(segments) > 1:
        # Add one conservative inter-city transfer per city boundary.
        budget_breakdown["transportation"] += 150 * max(request.travelers, 1) * (len(segments) - 1)

    budget_total = round(sum(budget_breakdown.values()), 2)
    return {
        "city": " -> ".join(segment["city"] for segment in segments),
        "cities": segments,
        "start_date": request.start_date,
        "days_count": total_days,
        "travelers": request.travelers,
        "preferences": request.preferences,
        "pace": request.pace,
        "accommodation": request.accommodation,
        "transportation": request.transportation,
        "itinerary_days": itinerary_days,
        "attractions": attractions,
        "restaurants": restaurants,
        "hotels": hotels,
        "travel_insights": {"ok": bool(notes), "notes": notes, "merged_insights": merged_insights},
        "weather": {
            "ok": weather_available_days > 0,
            "provider": "merged",
            "daily": weather_daily,
            "requested_days": total_days,
            "available_days": weather_available_days,
        },
        "budget": {"ok": True, "total": budget_total, "breakdown": budget_breakdown},
        "budget_check": {"ok": True, "over_budget": bool(request.max_budget and budget_total > request.max_budget)},
        "constraints": {"ok": True, "has_conflicts": has_conflicts, "conflicts": all_conflicts, "suggestions": suggestions},
        "packing": {"ok": bool(packing_days), "onion_layering_calendar": packing_days},
        "content": "",
    }


def _offset_date(value: str, days: int) -> str:
    try:
        return (date.fromisoformat(value) + timedelta(days=days)).isoformat()
    except ValueError:
        return value
