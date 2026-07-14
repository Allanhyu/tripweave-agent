"""Constraint checking tools for trip planning."""

from typing import Any, Dict, List

from app.core.tool import tool


@tool(description="检查行程是否存在时间过载、预算超支或路线过长风险。返回冲突列表和修改建议。")
def check_itinerary_constraints(
    itinerary_days: List[Dict[str, Any]],
    max_daily_minutes: int = 600,
    max_budget: float = 0,
    estimated_budget: float = 0,
) -> Dict[str, Any]:
    """Check simple time, route and budget constraints."""
    conflicts: List[Dict[str, Any]] = []
    suggestions: List[str] = []

    for day in itinerary_days:
        day_index = day.get("day", day.get("day_index", "?"))
        attractions = day.get("attractions") or []
        visit_minutes = sum(int(item.get("visit_minutes") or item.get("visit_duration") or 0) for item in attractions)
        transfer_minutes = sum(int(item.get("transfer_minutes") or 0) for item in attractions)
        total_minutes = visit_minutes + transfer_minutes

        if total_minutes > max_daily_minutes:
            conflicts.append({
                "type": "time_overload",
                "day": day_index,
                "total_minutes": total_minutes,
                "limit_minutes": max_daily_minutes,
            })
            suggestions.append(f"Day {day_index} 超过每日上限,建议删减1个景点或把远距离景点移到其他天。")

        long_transfers = [
            item.get("name", "unknown")
            for item in attractions
            if int(item.get("transfer_minutes") or 0) >= 60
        ]
        if long_transfers:
            conflicts.append({
                "type": "route_risk",
                "day": day_index,
                "attractions": long_transfers,
            })
            suggestions.append(f"Day {day_index} 存在长距离换乘,建议按地理邻近重排: {', '.join(long_transfers)}。")

    if max_budget > 0 and estimated_budget > max_budget:
        conflicts.append({
            "type": "budget_overrun",
            "estimated_budget": estimated_budget,
            "max_budget": max_budget,
            "over_by": round(estimated_budget - max_budget, 2),
        })
        suggestions.append("预算超支,优先降低住宿标准、减少收费景点或压缩餐饮预算。")

    return {
        "ok": True,
        "has_conflicts": bool(conflicts),
        "conflicts": conflicts,
        "suggestions": suggestions,
    }
