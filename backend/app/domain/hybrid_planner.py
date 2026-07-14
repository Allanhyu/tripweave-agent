"""Hybrid trip planner: fast deterministic path with ReAct fallback."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from math import atan2, cos, radians, sin, sqrt
from typing import Any, Callable, Dict, List, Optional

from app.core.cache import TTLCache
from app.domain.planner import TripPlanner
from app.domain.schemas import TripPlanningRequest, TripPlanningResponse
from app.tools.budget import check_budget_limit, estimate_trip_budget
from app.tools.constraints import check_itinerary_constraints
from app.tools.map import estimate_route, search_poi
from app.tools.packing import generate_packing_and_outfits
from app.tools.weather import get_weather_forecast
from app.tools.tavily import search_travel_notes


StepCallback = Optional[Callable[[dict], None]]

_TOOL_CACHE = TTLCache()
_POI_TTL_SECONDS = 30 * 60
_WEATHER_TTL_SECONDS = 10 * 60
_ROUTE_TTL_SECONDS = 30 * 60
_TRAVEL_RESEARCH_TTL_SECONDS = 60 * 60


def clear_tool_cache() -> None:
    _TOOL_CACHE.clear()


class HybridTripPlanner:
    """Fast planner for normal cases, ReAct planner for cases needing replanning."""

    def plan(self, request: TripPlanningRequest, on_step: StepCallback = None) -> TripPlanningResponse:
        fast_result = self._fast_plan(request, on_step=on_step)
        fallback_reasons = _fallback_reasons(fast_result.raw_steps)

        if fallback_reasons:
            fallback_step = _system_step(
                iteration=len(fast_result.raw_steps) + 1,
                thought="快速链路发现需要重新规划的问题,切换到 ReAct 深度规划。",
                observation={
                    "mode": "react_fallback",
                    "fallback_reasons": fallback_reasons,
                },
            )
            _emit_step(on_step, fallback_step)
            try:
                react_result = TripPlanner().plan(request, on_step=on_step)
                return TripPlanningResponse(
                    content=react_result.content,
                    step_count=len(fast_result.raw_steps) + 1 + react_result.step_count,
                    raw_steps=fast_result.raw_steps + [fallback_step] + react_result.raw_steps,
                    warning="Fallback to ReAct: " + "; ".join(fallback_reasons),
                )
            except Exception as error:
                content = _render_fast_content(request, fast_result.raw_steps)
                content += "\n\n### 深度重规划状态\n"
                content += f"- 已检测到需要重规划的问题: {'; '.join(fallback_reasons)}\n"
                content += f"- ReAct 深度规划暂时失败: {error}\n"
                raw_steps = fast_result.raw_steps + [fallback_step]
                return TripPlanningResponse(
                    content=content,
                    step_count=len(raw_steps),
                    raw_steps=raw_steps,
                    warning=f"ReAct fallback failed: {error}",
                )

        content = _render_fast_content(request, fast_result.raw_steps)
        final_step = {
            "iteration": len(fast_result.raw_steps) + 1,
            "thought": "快速链路没有发现预算、路线或天气风险,直接生成最终方案。",
            "action_type": "final_answer",
            "tool_name": None,
            "arguments": {},
            "observation": None,
            "raw_output": content,
        }
        _emit_step(on_step, final_step)
        raw_steps = fast_result.raw_steps + [final_step]
        return TripPlanningResponse(
            content=content,
            step_count=len(raw_steps),
            raw_steps=raw_steps,
            warning=None,
        )

    def _fast_plan(self, request: TripPlanningRequest, on_step: StepCallback = None) -> TripPlanningResponse:
        steps: List[dict] = []
        iteration = 1
        keyword = ", ".join(request.preferences) if request.preferences else "景点"

        target_attraction_count = max(request.days * 4, 8)
        poi_args = {"city": request.city, "keyword": keyword, "limit": min(target_attraction_count, 25)}
        poi_result, poi_meta = _cached_tool_call("search_poi", poi_args, _POI_TTL_SECONDS, search_poi)
        poi_result = _filter_attraction_pois(poi_result)
        if not request.preferences:
            poi_result = _diversify_default_pois(poi_result)
        _append_step(steps, on_step, _tool_step(
            iteration=iteration,
            thought="快速链路先搜索真实POI作为行程候选。",
            tool_name="search_poi",
            arguments=poi_args,
            observation=poi_result,
            metadata={**poi_meta, "purpose": "attractions"},
        ))
        iteration += 1

        needs_supplement = _usable_poi_count(poi_result) < max(request.days * 3, 1)
        supplement_args = {
            "city": request.city,
            "keyword": "历史文化街区 古镇 步行街 地标" if not request.preferences else "景点",
            "limit": 8,
        }
        food_args = {"city": request.city, "keyword": _food_keyword(request), "limit": 5}
        hotel_args = {"city": request.city, "keyword": _hotel_keyword(request), "limit": 5}
        weather_args = {"city": request.city, "days": request.days, "start_date": request.start_date}
        research_args = {
            "city": request.city,
            "keywords": ", ".join(request.preferences) if request.preferences else "旅游 攻略 避坑 预约",
            "limit": 5,
        }
        parallel_specs = {
            "restaurants": ("search_poi", food_args, _POI_TTL_SECONDS, search_poi),
            "hotels": ("search_poi", hotel_args, _POI_TTL_SECONDS, search_poi),
            "weather": ("get_weather_forecast", weather_args, _WEATHER_TTL_SECONDS, get_weather_forecast),
            "travel_insights": ("search_travel_notes", research_args, _TRAVEL_RESEARCH_TTL_SECONDS, search_travel_notes),
        }
        if needs_supplement:
            parallel_specs["supplemental_attractions"] = ("search_poi", supplement_args, _POI_TTL_SECONDS, search_poi)

        parallel_results = _run_parallel_cached_calls(parallel_specs)

        if needs_supplement:
            supplement_result, supplement_meta = parallel_results["supplemental_attractions"]
            _append_step(steps, on_step, _tool_step(
                iteration=iteration,
                thought="主关键词去重后景点不足,补充搜索通用景点以保证每日行程完整。",
                tool_name="search_poi",
                arguments=supplement_args,
                observation=supplement_result,
                metadata={**supplement_meta, "purpose": "supplemental_attractions"},
            ))
            poi_result = _merge_poi_results(poi_result, supplement_result)
            poi_result = _filter_attraction_pois(poi_result)
            if not request.preferences:
                poi_result = _diversify_default_pois(poi_result)
            iteration += 1

        food_result, food_meta = parallel_results["restaurants"]
        hotel_result, hotel_meta = parallel_results["hotels"]
        weather_result, weather_meta = parallel_results["weather"]
        research_result, research_meta = parallel_results["travel_insights"]

        for thought, tool_name, args, result, meta in [
            ("快速链路补充餐饮候选,用于安排午餐和晚餐。", "search_poi", food_args, food_result, {**food_meta, "purpose": "restaurants"}),
            ("快速链路补充住宿候选,用于给出落脚区域建议。", "search_poi", hotel_args, hotel_result, {**hotel_meta, "purpose": "hotels"}),
            ("快速链路查询真实天气,用于穿搭和天气风险判断。", "get_weather_forecast", weather_args, weather_result, weather_meta),
            ("公开旅行攻略检索,用于补充候选景点、避坑点和预约提醒。", "search_travel_notes", research_args, research_result, {**research_meta, "purpose": "travel_insights"}),
        ]:
            _append_step(steps, on_step, _tool_step(
                iteration=iteration,
                thought=thought,
                tool_name=tool_name,
                arguments=args,
                observation=result,
                metadata=meta,
            ))
            iteration += 1

        research_poi_result = _resolve_research_candidate_pois(request, research_result)
        _append_step(steps, on_step, _tool_step(
            iteration=iteration,
            thought="将公开攻略候选景点解析为高德真实POI,并提升到行程候选池前列。",
            tool_name="search_poi",
            arguments={
                "city": request.city,
                "candidate_names": research_poi_result.get("candidate_names", []),
            },
            observation=research_poi_result,
            metadata={"purpose": "research_candidate_attractions", "source": "travel_insights"},
        ))
        iteration += 1
        if research_poi_result.get("ok"):
            poi_result = _merge_poi_results(research_poi_result, poi_result)
        poi_result = _filter_attraction_pois(poi_result)
        if not request.preferences:
            poi_result = _diversify_default_pois(poi_result)

        itinerary_days = _build_itinerary_days(request, poi_result)
        route_results = _estimate_selected_routes(request, itinerary_days)
        for route_args, route_result, route_meta in route_results:
            _append_step(steps, on_step, _tool_step(
                iteration=iteration,
                thought="快速链路估算同日相邻地点的移动成本。",
                tool_name="estimate_route",
                arguments=route_args,
                observation=route_result,
                metadata=route_meta,
            ))
            iteration += 1

        _merge_route_minutes(itinerary_days, route_results)
        budget_args = {
            "days": request.days,
            "attractions_cost_per_day": _estimate_attraction_cost(request, poi_result),
            "meals_cost_per_day": 120 * max(request.travelers, 1),
            "hotel_cost_per_night": _hotel_cost(request.accommodation) * max((request.travelers + 1) // 2, 1),
            "transportation_total": _transportation_total(route_results, request.days, request.travelers),
            "misc_total": 60 * max(request.travelers, 1),
        }
        budget_result, budget_meta = _timed_tool_call(estimate_trip_budget, budget_args)
        _append_step(steps, on_step, _tool_step(
            iteration=iteration,
            thought="快速链路根据默认价格模型估算总预算。",
            tool_name="estimate_trip_budget",
            arguments=budget_args,
            observation=budget_result,
            metadata=budget_meta,
        ))
        iteration += 1

        if request.max_budget > 0:
            budget_check_args = {"budget_result": budget_result, "max_budget": request.max_budget}
            budget_check, budget_check_meta = _timed_tool_call(check_budget_limit, budget_check_args)
            _append_step(steps, on_step, _tool_step(
                iteration=iteration,
                thought="快速链路检查预算是否超过用户上限。",
                tool_name="check_budget_limit",
                arguments=budget_check_args,
                observation=budget_check,
                metadata=budget_check_meta,
            ))
            iteration += 1

        constraint_args = {
            "itinerary_days": itinerary_days,
            "max_daily_minutes": _daily_limit(request.pace),
            "max_budget": request.max_budget,
            "estimated_budget": float(budget_result.get("total") or 0),
        }
        constraint_result, constraint_meta = _timed_tool_call(check_itinerary_constraints, constraint_args)
        _append_step(steps, on_step, _tool_step(
            iteration=iteration,
            thought="快速链路检查每日时间、路线和预算风险。",
            tool_name="check_itinerary_constraints",
            arguments=constraint_args,
            observation=constraint_result,
            metadata=constraint_meta,
        ))
        iteration += 1

        if request.include_packing:
            packing_args = {
                "weather_daily": (weather_result.get("daily") if weather_result.get("ok") else []) or [],
                "itinerary_days": itinerary_days,
            }
            packing_result, packing_meta = _timed_tool_call(generate_packing_and_outfits, packing_args)
            _append_step(steps, on_step, _tool_step(
                iteration=iteration,
                thought="快速链路基于天气和行程生成行李清单与洋葱穿衣法。",
                tool_name="generate_packing_and_outfits",
                arguments=packing_args,
                observation=packing_result,
                metadata=packing_meta,
            ))

        return TripPlanningResponse(content="", step_count=len(steps), raw_steps=steps)


def _append_step(steps: List[dict], on_step: StepCallback, step: dict) -> None:
    steps.append(step)
    _emit_step(on_step, step)


def _emit_step(on_step: StepCallback, step: dict) -> None:
    if on_step:
        on_step(step)


def _tool_step(
    iteration: int,
    thought: str,
    tool_name: str,
    arguments: Dict[str, Any],
    observation: Any,
    metadata: Optional[Dict[str, Any]] = None,
) -> dict:
    return {
        "iteration": iteration,
        "thought": thought,
        "action_type": "tool_call",
        "tool_name": tool_name,
        "arguments": arguments,
        "observation": observation,
        "metadata": metadata or {},
        "raw_output": "",
    }


def _system_step(iteration: int, thought: str, observation: Any) -> dict:
    return {
        "iteration": iteration,
        "thought": thought,
        "action_type": "system",
        "tool_name": "fallback_decision",
        "arguments": {},
        "observation": observation,
        "metadata": {},
        "raw_output": "",
    }


def _cached_tool_call(tool_name: str, arguments: Dict[str, Any], ttl_seconds: int, func) -> tuple:
    started = time.perf_counter()
    hit, cached_value = _TOOL_CACHE.get(tool_name, arguments)
    if hit:
        return cached_value, {
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            "cache_hit": True,
            "ttl_seconds": ttl_seconds,
        }

    value = func(**arguments)
    cache_saved = not (isinstance(value, dict) and value.get("ok") is False)
    if cache_saved:
        _TOOL_CACHE.set(tool_name, arguments, value, ttl_seconds)
    return value, {
        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        "cache_hit": False,
        "cache_saved": cache_saved,
        "ttl_seconds": ttl_seconds,
    }


def _run_parallel_cached_calls(call_specs: Dict[str, tuple]) -> Dict[str, tuple]:
    results: Dict[str, tuple] = {}
    max_workers = min(len(call_specs), 4) or 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_cached_tool_call, tool_name, args, ttl_seconds, func): name
            for name, (tool_name, args, ttl_seconds, func) in call_specs.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            results[name] = future.result()
    return results


def _timed_tool_call(func, arguments: Dict[str, Any]) -> tuple:
    started = time.perf_counter()
    value = func(**arguments)
    return value, {
        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        "cache_hit": False,
    }


def _filter_attraction_pois(result: Dict[str, Any]) -> Dict[str, Any]:
    """Remove commercial/service POIs that AMap loosely matches to 景点."""
    if not result.get("ok"):
        return result

    attraction_hints = [
        "风景名胜", "旅游景点", "景区", "公园", "森林", "湿地", "植物园", "动物园",
        "博物馆", "纪念馆", "展馆", "美术馆", "古迹", "古镇", "寺", "塔", "故居",
        "历史文化", "步行街", "街区", "地标", "广场", "山", "湖", "岛", "海滩",
    ]
    service_types = [
        "购物服务", "餐饮服务", "住宿服务", "生活服务", "商务住宅", "医疗保健服务",
        "交通设施服务", "汽车服务", "金融保险服务",
    ]
    blocked_names = [
        "便利店", "超市", "商场", "购物中心", "餐厅", "饭店", "烧烤", "酒店", "宾馆",
        "银行", "药店", "加油站", "停车场", "维修", "洗车", "快递", "诊所", "医院",
        "学校", "营业厅", "五金", "建材", "专卖店", "零售", "批发", "门市",
    ]

    def is_attraction(poi: Dict[str, Any]) -> bool:
        name = str(poi.get("name") or "").strip()
        poi_type = str(poi.get("type") or "")
        text = f"{name}{poi_type}"
        if not name or any(word in name for word in blocked_names):
            return False
        if any(service_type in poi_type for service_type in service_types):
            return any(hint in name for hint in attraction_hints)
        return any(hint in text for hint in attraction_hints)

    pois = [poi for poi in (result.get("pois") or []) if is_attraction(poi)]
    return {**result, "pois": pois, "attraction_filter": "strict"}


def _build_itinerary_days(request: TripPlanningRequest, poi_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    pois = poi_result.get("pois") if poi_result.get("ok") else []
    if not pois:
        pois = [{"name": "城市核心区", "address": request.city}]

    ranked_pois = _rank_pois_for_itinerary(_dedupe_pois(pois))
    # The normal pace targets four stops per day; relaxed trips target three.
    target_per_day = 3 if request.pace == "relaxed" else 4
    available_per_day = max(1, len(ranked_pois) // max(request.days, 1))
    target_per_day = min(target_per_day, available_per_day)
    selected = ranked_pois[:max(request.days * target_per_day, 1)]
    itinerary_days = []
    for day_index in range(request.days):
        day_pois = selected[day_index * target_per_day:(day_index + 1) * target_per_day] or selected[:1]
        attractions = []
        for item_index, poi in enumerate(day_pois):
            attractions.append({
                "name": poi.get("name", "未知地点"),
                "address": poi.get("address", ""),
                "type": poi.get("type", ""),
                "cost": poi.get("cost"),
                "visit_minutes": 120 if item_index == 0 else 90,
                "transfer_minutes": 0 if item_index == 0 else 20,
                "rating": poi.get("rating"),
                "location": poi.get("location"),
                "research_source": bool(poi.get("research_source")),
                "research_candidate_name": poi.get("research_candidate_name"),
            })
        itinerary_days.append({"day": day_index + 1, "attractions": attractions})
    return itinerary_days


def _resolve_research_candidate_pois(request: TripPlanningRequest, research_result: Dict[str, Any]) -> Dict[str, Any]:
    if not research_result.get("ok"):
        return {
            "ok": False,
            "provider": "research_candidate_poi",
            "city": request.city,
            "keyword": "research_candidates",
            "pois": [],
            "candidate_names": [],
            "error": research_result.get("error") or "travel research unavailable",
        }

    insights = research_result.get("merged_insights") or {}
    candidate_names = _unique_candidate_names(insights.get("candidate_attractions") or [])
    candidate_names = candidate_names[: min(4, max(request.days * 2, 2))]
    pois: List[Dict[str, Any]] = []
    errors: List[str] = []

    for name in candidate_names:
        result, _meta = _cached_tool_call(
            "search_poi",
            {"city": request.city, "keyword": name, "limit": 1},
            _POI_TTL_SECONDS,
            search_poi,
        )
        if result.get("ok") and result.get("pois"):
            poi = dict(result["pois"][0])
            poi["research_source"] = True
            poi["research_candidate_name"] = name
            pois.append(poi)
        elif not result.get("ok"):
            errors.append(f"{name}: {result.get('error') or 'search failed'}")

    return {
        "ok": bool(pois),
        "provider": "research_candidate_poi",
        "city": request.city,
        "keyword": "research_candidates",
        "pois": pois,
        "candidate_names": candidate_names,
        "errors": errors,
        "error": "" if pois else "no travel research candidate matched real POI",
    }


def _unique_candidate_names(items: List[Any]) -> List[str]:
    result: List[str] = []
    seen = set()
    for item in items:
        name = str(item or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


def _rank_pois_for_itinerary(pois: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    research_pois = [poi for poi in pois if poi.get("research_source")]
    other_pois = [poi for poi in pois if not poi.get("research_source")]
    return _rank_poi_group(research_pois) + _rank_poi_group(other_pois)


def _rank_poi_group(pois: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ordered = _sort_pois_by_neighborhood(pois)
    attraction_suffixes = (
        "景区", "古城", "古镇", "博物馆", "纪念馆", "故居", "遗址", "寺", "塔",
        "动物园", "植物园", "长城", "山", "湖", "岛", "广场",
    )

    def score(poi: Dict[str, Any]) -> tuple:
        name = str(poi.get("name") or "")
        poi_type = str(poi.get("type") or "")
        rating = 0.0
        try:
            rating = float(poi.get("rating") or 0)
        except (TypeError, ValueError):
            pass
        official_shape = int(any(name.endswith(suffix) for suffix in attraction_suffixes))
        scenic_type = int("风景名胜" in poi_type or "科教文化" in poi_type)
        return official_shape + scenic_type, rating

    return sorted(ordered, key=score, reverse=True)


def _remove_default_museum_bias(result: Dict[str, Any]) -> Dict[str, Any]:
    """Avoid turning an empty preference into an implicit museum preference."""
    if not result.get("ok"):
        return result
    pois = result.get("pois") or []
    non_museum = [
        poi for poi in pois
        if not any(word in str(poi.get("name") or "") for word in ["博物馆", "博物院", "纪念馆", "展览馆", "美术馆"])
    ]
    if not non_museum:
        return result
    return {**result, "pois": non_museum}


def _diversify_default_pois(result: Dict[str, Any]) -> Dict[str, Any]:
    """Keep generic recommendations from becoming a park-only list."""
    filtered = _remove_default_museum_bias(result)
    if not filtered.get("ok"):
        return filtered
    pois = filtered.get("pois") or []
    blocked_words = ["停车场", "停车服务", "检票处", "售票处", "游客中心", "洗手间", "加油站"]
    useful_pois = [
        poi for poi in pois
        if not any(word in f"{poi.get('name') or ''}{poi.get('type') or ''}" for word in blocked_words)
    ]
    if useful_pois:
        pois = useful_pois
    nature_words = ["公园", "森林", "湿地", "植物园", "郊野", "园林"]
    nature = [
        poi for poi in pois
        if any(word in f"{poi.get('name') or ''}{poi.get('type') or ''}" for word in nature_words)
    ]
    other = [
        poi for poi in pois
        if not any(word in f"{poi.get('name') or ''}{poi.get('type') or ''}" for word in nature_words)
    ]
    if not other or len(nature) <= 1:
        return filtered
    max_nature = max(1, len(pois) // 3)
    return {**filtered, "pois": other + nature[:max_nature]}


def _dedupe_pois(pois: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    seen_keys = set()
    parent_names = set()

    for poi in pois:
        name = str(poi.get("name") or "").strip()
        address = str(poi.get("address") or "").strip()
        if not name:
            continue

        parent = _parent_poi_name(name)
        normalized = _normalize_text(parent or name)
        address_key = _normalize_text(address)
        location = poi.get("location") or {}
        geo_key = (
            round(float(location.get("longitude") or 0), 3),
            round(float(location.get("latitude") or 0), 3),
        )
        key = (normalized, address_key, geo_key)

        if key in seen_keys:
            continue
        if parent and parent in parent_names and parent != name:
            continue
        if any(_is_sub_poi(name, kept.get("name", "")) for kept in result):
            continue

        seen_keys.add(key)
        parent_names.add(parent or name)
        result.append(poi)

    return result or pois[:]


def _usable_poi_count(poi_result: Dict[str, Any]) -> int:
    if not poi_result.get("ok"):
        return 0
    return len(_dedupe_pois(poi_result.get("pois") or []))


def _merge_poi_results(primary: Dict[str, Any], supplemental: Dict[str, Any]) -> Dict[str, Any]:
    if not primary.get("ok"):
        return supplemental
    if not supplemental.get("ok"):
        return primary

    merged = dict(primary)
    merged["pois"] = _dedupe_pois((primary.get("pois") or []) + (supplemental.get("pois") or []))
    merged["supplemental_keyword"] = supplemental.get("keyword")
    return merged


def _sort_pois_by_neighborhood(pois: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    with_location = [poi for poi in pois if _poi_location_tuple(poi)]
    without_location = [poi for poi in pois if not _poi_location_tuple(poi)]
    if len(with_location) <= 2:
        return pois

    ordered = [with_location[0]]
    remaining = with_location[1:]
    while remaining:
        current = ordered[-1]
        next_poi = min(remaining, key=lambda poi: _rough_distance(current, poi))
        ordered.append(next_poi)
        remaining.remove(next_poi)
    return ordered + without_location


def _parent_poi_name(name: str) -> str:
    for separator in ["-", "—", "·", "("]:
        if separator in name:
            return name.split(separator, 1)[0].strip()
    return name


def _normalize_text(value: str) -> str:
    return "".join(value.lower().replace(" ", "").split())


def _is_sub_poi(candidate: str, existing: str) -> bool:
    parent = _parent_poi_name(candidate)
    return bool(parent and parent != candidate and parent == _parent_poi_name(existing))


def _poi_location_tuple(poi: Dict[str, Any]) -> Optional[tuple]:
    location = poi.get("location") or {}
    lng = location.get("longitude")
    lat = location.get("latitude")
    if lng is None or lat is None:
        return None
    return float(lng), float(lat)


def _rough_distance(first: Dict[str, Any], second: Dict[str, Any]) -> float:
    first_loc = _poi_location_tuple(first)
    second_loc = _poi_location_tuple(second)
    if not first_loc or not second_loc:
        return 999999
    return abs(first_loc[0] - second_loc[0]) + abs(first_loc[1] - second_loc[1])


def _estimate_selected_routes(
    request: TripPlanningRequest,
    itinerary_days: List[Dict[str, Any]],
) -> List[tuple]:
    route_jobs = []
    for index, day in enumerate(itinerary_days):
        attractions = day.get("attractions") or []
        if len(attractions) < 2:
            continue
        origin = _route_endpoint(attractions[0])
        destination = _route_endpoint(attractions[1])
        args = {
            "origin": origin,
            "destination": destination,
            "city": request.city,
            "mode": "walking" if request.transportation == "walking first" else "driving",
        }
        route_jobs.append((index, args))

    route_results: List[Optional[tuple]] = [None] * len(route_jobs)
    if not route_jobs:
        return []

    with ThreadPoolExecutor(max_workers=min(len(route_jobs), 4)) as executor:
        futures = {executor.submit(_fast_route_call, args): index for index, (_, args) in enumerate(route_jobs)}
        for future in as_completed(futures):
            result_index = futures[future]
            args = route_jobs[result_index][1]
            route_result, route_meta = future.result()
            route_results[result_index] = (args, route_result, route_meta)

    return [item for item in route_results if item is not None]


def _route_endpoint(attraction: Dict[str, Any]) -> str:
    location = attraction.get("location") or {}
    lng = location.get("longitude")
    lat = location.get("latitude")
    if lng is not None and lat is not None:
        return f"{lng},{lat}"
    return attraction.get("name") or attraction.get("address") or ""


def _fast_route_call(args: Dict[str, Any]) -> tuple:
    started = time.perf_counter()
    rough_result = _rough_route_result(args["origin"], args["destination"], args.get("mode", "driving"))
    if rough_result:
        return rough_result, {
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            "cache_hit": False,
            "route_strategy": "coordinate_rough_estimate",
        }

    route_result, route_meta = _cached_tool_call("estimate_route", args, _ROUTE_TTL_SECONDS, estimate_route)
    return route_result, {**route_meta, "route_strategy": "amap_fallback"}


def _rough_route_result(origin: str, destination: str, mode: str) -> Optional[Dict[str, Any]]:
    origin_loc = _parse_location_string(origin)
    destination_loc = _parse_location_string(destination)
    if not origin_loc or not destination_loc:
        return None

    distance_km = _haversine_km(origin_loc, destination_loc)
    detour_factor = 1.15 if mode == "walking" else 1.3
    speed_kmh = 4.8 if mode == "walking" else 22
    distance_meters = distance_km * detour_factor * 1000
    duration_minutes = max(5, distance_km * detour_factor / speed_kmh * 60)
    if mode != "walking":
        duration_minutes += 6

    return {
        "ok": True,
        "provider": "coordinate_rough_estimate",
        "mode": mode,
        "mode_used": mode,
        "origin": origin,
        "destination": destination,
        "distance_meters": round(distance_meters, 1),
        "duration_minutes": round(duration_minutes, 1),
        "note": "基于真实POI经纬度的快速粗估,用于规划阶段约束判断。",
    }


def _parse_location_string(value: str) -> Optional[tuple]:
    if not value or "," not in value:
        return None
    lng, lat = value.split(",", 1)
    try:
        return float(lng), float(lat)
    except ValueError:
        return None


def _haversine_km(origin: tuple, destination: tuple) -> float:
    lng1, lat1 = origin
    lng2, lat2 = destination
    radius_km = 6371
    d_lat = radians(lat2 - lat1)
    d_lng = radians(lng2 - lng1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lng / 2) ** 2
    return 2 * radius_km * atan2(sqrt(a), sqrt(1 - a))


def _merge_route_minutes(itinerary_days: List[Dict[str, Any]], route_results: List[tuple]) -> None:
    for day, (_, result, _) in zip(itinerary_days, route_results):
        attractions = day.get("attractions") or []
        if len(attractions) >= 2 and result.get("ok"):
            attractions[1]["transfer_minutes"] = int(result.get("duration_minutes") or 30)


def _estimate_attraction_cost(request: TripPlanningRequest, poi_result: Dict[str, Any]) -> float:
    pois = poi_result.get("pois") or []
    attractions_per_day = max(1, min(3, (len(pois) + max(request.days, 1) - 1) // max(request.days, 1)))
    ticket_costs = []
    for poi in pois:
        try:
            cost = float(poi.get("cost") or 0)
        except (TypeError, ValueError):
            cost = 0
        if cost > 0:
            ticket_costs.append(cost)
    average_ticket = sum(ticket_costs) / len(ticket_costs) if ticket_costs else 35
    return round(average_ticket * attractions_per_day, 2)


def _hotel_cost(accommodation: str) -> float:
    if "budget" in accommodation:
        return 180
    if "boutique" in accommodation:
        return 450
    return 300


def _transportation_total(route_results: List[tuple], days: int, travelers: int) -> float:
    route_count = max(len(route_results), days)
    return route_count * 20 * max(travelers, 1)


def _food_keyword(request: TripPlanningRequest) -> str:
    preferences = ",".join(request.preferences)
    if any(word in preferences for word in ["美食", "餐厅", "米其林"]):
        return preferences
    return "特色餐厅"


def _hotel_keyword(request: TripPlanningRequest) -> str:
    if "budget" in request.accommodation:
        return "经济型酒店"
    if "boutique" in request.accommodation:
        return "精品酒店"
    return "酒店"


def _daily_limit(pace: str) -> int:
    if pace == "relaxed":
        return 480
    if pace == "intensive":
        return 660
    return 570


def _fallback_reasons(steps: List[dict]) -> List[str]:
    reasons: List[str] = []
    for step in steps:
        tool_name = step.get("tool_name")
        observation = step.get("observation") or {}
        if not isinstance(observation, dict):
            continue
        if tool_name == "get_weather_forecast" and observation.get("ok") and _has_weather_risk(observation):
            reasons.append("weather risk detected")
        if tool_name == "check_budget_limit" and observation.get("over_budget"):
            reasons.append("budget overrun")
        if tool_name == "check_itinerary_constraints" and observation.get("has_conflicts"):
            reasons.append("itinerary conflicts")
    return reasons


def _has_weather_risk(weather_result: Dict[str, Any]) -> bool:
    if not weather_result.get("ok"):
        return True
    for day in weather_result.get("daily") or []:
        desc = str(day.get("day_weather") or day.get("night_weather") or "")
        temp_max = float(day.get("temp_max") or 0)
        temp_min = float(day.get("temp_min") or 0)
        if any(keyword in desc for keyword in ["暴雨", "大雨", "雷雨", "雪", "storm"]):
            return True
        if temp_max >= 41 or temp_min <= -10:
            return True
    return False


def _render_fast_content(request: TripPlanningRequest, steps: List[dict]) -> str:
    research_poi_result = _observation_by_purpose(steps, "research_candidate_attractions") or {}
    poi_result = _observation_by_purpose(steps, "attractions") or {}
    supplemental_poi_result = _observation_by_purpose(steps, "supplemental_attractions") or {}
    if research_poi_result:
        poi_result = _merge_poi_results(research_poi_result, poi_result)
    if supplemental_poi_result:
        poi_result = _merge_poi_results(poi_result, supplemental_poi_result)
    food_result = _observation_by_purpose(steps, "restaurants") or {}
    hotel_result = _observation_by_purpose(steps, "hotels") or {}
    research_result = _observation_by_purpose(steps, "travel_insights") or {}
    weather_result = _observation_by_tool(steps, "get_weather_forecast") or {}
    budget_result = _observation_by_tool(steps, "estimate_trip_budget") or {}
    budget_check = _observation_by_tool(steps, "check_budget_limit") or {}
    constraint_result = _observation_by_tool(steps, "check_itinerary_constraints") or {}
    packing_result = _observation_by_tool(steps, "generate_packing_and_outfits") or {}
    itinerary_days = ((steps[-2] if len(steps) >= 2 else {}).get("arguments") or {}).get("itinerary_days") or []
    if not itinerary_days:
        itinerary_days = _build_itinerary_days(request, poi_result)
    restaurants = food_result.get("pois") or []
    hotels = hotel_result.get("pois") or []

    lines = [
        f"## {request.city}{request.days}日快速旅行规划",
        "",
        "### 规划模式",
        "本次未发现预算超支、路线冲突或异常天气,采用快速链路生成;未进入 ReAct 深度重规划。",
        "本阶段已做 POI 去重、相邻地点排序,并补充餐饮和住宿候选。",
        "",
        "### 每日行程",
    ]

    weather_daily = weather_result.get("daily") or []
    for day in itinerary_days:
        day_index = day.get("day")
        weather = weather_daily[day_index - 1] if isinstance(day_index, int) and day_index - 1 < len(weather_daily) else {}
        weather_text = ""
        if weather:
            weather_text = f"（{weather.get('day_weather', '')}, {weather.get('temp_min')}~{weather.get('temp_max')}℃）"
        attractions = day.get("attractions") or []
        lunch = _pick_by_index(restaurants, day_index - 1)
        dinner = _pick_by_index(restaurants, day_index)
        hotel = _pick_by_index(hotels, day_index - 1)
        lines.append(f"#### Day {day_index} {weather_text}")
        if attractions:
            first = attractions[0]
            lines.append(
                f"- 09:00-11:30 上午核心游览: {first.get('name')}。"
                f"{first.get('address', '')}。建议游览约{first.get('visit_minutes')}分钟。"
            )
        if lunch:
            lines.append(f"- 12:00-13:00 午餐候选: {lunch.get('name')}。{lunch.get('address', '')}。")
        if len(attractions) >= 2:
            second = attractions[1]
            lines.append(
                f"- 13:30-16:00 下午邻近游览: {second.get('name')}。"
                f"从上一地点转移约{second.get('transfer_minutes')}分钟。{second.get('address', '')}。"
            )
        if dinner:
            lines.append(f"- 18:00-19:30 晚餐候选: {dinner.get('name')}。{dinner.get('address', '')}。")
        if hotel:
            lines.append(f"- 住宿建议: {hotel.get('name')}。{hotel.get('address', '')}。")

    lines.extend([
        "",
        "### 真实地点依据",
    ])
    for poi in _dedupe_pois(poi_result.get("pois") or [])[:5]:
        lines.append(f"- {poi.get('name')}：{poi.get('address')}，评分 {poi.get('rating') or '暂无'}")

    if research_result:
        insights = research_result.get("merged_insights") or {}
        lines.extend(["", "### 公开旅行攻略洞察"])
        if research_result.get("ok"):
            for note in (research_result.get("notes") or [])[:3]:
                lines.append(f"- {note.get('title')}: {note.get('summary')} {note.get('url') or ''}".strip())
        else:
            lines.append(f"- 公开旅行攻略暂未接入成功: {research_result.get('error') or '无结果'}")
        for label, key in [
            ("候选景点", "candidate_attractions"),
            ("避坑点", "pitfalls"),
            ("预约提醒", "reservation_tips"),
        ]:
            values = insights.get(key) or []
            if values:
                lines.append(f"- {label}: {'; '.join(values[:6])}")

    lines.extend(["", "### 餐饮候选"])
    for poi in restaurants[:5]:
        lines.append(f"- {poi.get('name')}：{poi.get('address')}，评分 {poi.get('rating') or '暂无'}")

    lines.extend(["", "### 住宿候选"])
    for poi in hotels[:5]:
        lines.append(f"- {poi.get('name')}：{poi.get('address')}，评分 {poi.get('rating') or '暂无'}")

    lines.extend([
        "",
        "### 预算摘要",
        f"- 预计总费用：{budget_result.get('total', '未知')} 元",
        f"- 预算检查：{'超支' if budget_check.get('over_budget') else '预算内'}",
        "",
        "### 冲突/调整说明",
        "- 当前快速检查未发现明显冲突。" if not constraint_result.get("has_conflicts") else f"- {constraint_result.get('suggestions')}",
    ])

    if packing_result:
        lines.extend(["", "### 行李清单"])
        checklist = packing_result.get("checklist") or {}
        for category, items in checklist.items():
            lines.append(f"- {category}: {', '.join(items)}")
        lines.extend(["", "### 洋葱穿衣法日历"])
        for outfit in packing_result.get("onion_layering_calendar") or []:
            lines.append(
                f"- Day {outfit.get('day')}（{outfit.get('weather')} {outfit.get('temperature')}）：{outfit.get('outfit')}"
            )

    return "\n".join(lines)


def _observation_by_tool(steps: List[dict], tool_name: str) -> Any:
    for step in steps:
        if step.get("tool_name") == tool_name:
            return step.get("observation")
    return None


def _observation_by_purpose(steps: List[dict], purpose: str) -> Any:
    for step in steps:
        metadata = step.get("metadata") or {}
        if metadata.get("purpose") == purpose:
            return step.get("observation")
    return None


def _pick_by_index(items: List[Dict[str, Any]], index: int) -> Optional[Dict[str, Any]]:
    if not items:
        return None
    return items[index % len(items)]
