"""Budget tools for the handwritten Agent."""

from typing import Any, Dict, List

from app.core.tool import tool


@tool(description="估算旅行总预算。输入每天的景点、餐饮、住宿、交通费用,返回分类合计和总额。")
def estimate_trip_budget(
    days: int,
    attractions_cost_per_day: float = 0,
    meals_cost_per_day: float = 0,
    hotel_cost_per_night: float = 0,
    transportation_total: float = 0,
    misc_total: float = 0,
) -> Dict[str, Any]:
    """Estimate total travel budget from category-level costs."""
    nights = max(days - 1, 0)
    total_attractions = attractions_cost_per_day * days
    total_meals = meals_cost_per_day * days
    total_hotels = hotel_cost_per_night * nights
    total = total_attractions + total_meals + total_hotels + transportation_total + misc_total

    return {
        "ok": True,
        "days": days,
        "nights": nights,
        "breakdown": {
            "attractions": round(total_attractions, 2),
            "meals": round(total_meals, 2),
            "hotels": round(total_hotels, 2),
            "transportation": round(transportation_total, 2),
            "misc": round(misc_total, 2),
        },
        "total": round(total, 2),
    }


@tool(description="检查旅行预算是否超支。输入预算估算结果和预算上限,返回是否超支以及调整建议。")
def check_budget_limit(budget_result: Dict[str, Any], max_budget: float) -> Dict[str, Any]:
    """Check whether an estimated budget exceeds the user's limit."""
    total = float(budget_result.get("total") or 0)
    remaining = max_budget - total
    over_budget = remaining < 0
    suggestions: List[str] = []

    if over_budget:
        breakdown = budget_result.get("breakdown") or {}
        sorted_items = sorted(breakdown.items(), key=lambda item: float(item[1] or 0), reverse=True)
        for name, value in sorted_items[:3]:
            suggestions.append(f"优先压缩{name}费用,当前约{value}元")
    else:
        suggestions.append(f"预算内可用余额约{round(remaining, 2)}元")

    return {
        "ok": True,
        "max_budget": max_budget,
        "total": round(total, 2),
        "remaining": round(remaining, 2),
        "over_budget": over_budget,
        "suggestions": suggestions,
    }
