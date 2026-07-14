"""HTTP routes for TripWeave Agent."""

from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import Response

from app.api.jobs import trip_job_store
from app.api.schemas import TripPlanRequestBody, TripPlanResponseBody, UserMemoryBody
from app.domain.hybrid_planner import (
    HybridTripPlanner,
    _diversify_default_pois,
    _filter_attraction_pois,
    clear_tool_cache,
)
from app.domain.knowledge_graph import build_knowledge_graph
from app.domain.multi_city import execute_trip_plan
from app.domain.schemas import TripPlanningRequest
from app.domain.user_memory import (
    load_user_memory,
    memory_from_request,
    merge_request_with_memory,
    reset_user_memory,
    save_user_memory,
)
from app.runtime_settings import load_backend_env, save_runtime_settings, setting_status
from app.tools import create_default_tool_registry
from app.tools.map import (
    _env_value,
    estimate_route,
    geocode,
    search_poi,
    static_map_from_locations,
    static_map_from_pois,
)
from app.tools.tavily import search_travel_notes


router = APIRouter()


@router.get("/health")
def health():
    return {
        "status": "ok",
        "service": "tripweave-agent",
    }


@router.get("/api/map/config")
def map_config():
    """Expose only browser-safe AMap JS settings; service keys stay server-side."""
    env = load_backend_env()
    return {
        "amap_js_key": _env_value(env, "AMAP_WEB_JS_KEY"),
        "amap_security_js_code": _env_value(env, "AMAP_SECURITY_JS_CODE"),
    }


@router.get("/api/settings")
def get_runtime_settings():
    """Return editable settings metadata without exposing secret values."""
    return {"success": True, "data": setting_status(load_backend_env())}


@router.post("/api/settings")
def update_runtime_settings(payload: Dict[str, Any] = Body(...)):
    """Save local-only runtime overrides from the settings panel."""
    save_runtime_settings(payload)
    clear_tool_cache()
    return {"success": True, "data": setting_status(load_backend_env())}


@router.get("/api/tools")
def list_tools():
    registry = create_default_tool_registry()
    return {
        "success": True,
        "tools": registry.schemas(),
    }


@router.get("/api/map/poi")
def map_poi(
    city: str = Query(...),
    keyword: str = Query("景点"),
    limit: int = Query(8, ge=1, le=25),
):
    result = search_poi(city=city, keyword=keyword, limit=min(limit * 2, 25))
    attraction_keywords = {"景点", "旅游", "博物馆", "公园", "古镇", "古城", "地标"}
    if any(token in keyword for token in attraction_keywords):
        result = _diversify_default_pois(_filter_attraction_pois(result))
    if result.get("ok"):
        result["pois"] = (result.get("pois") or [])[:limit]
    return result


@router.get("/api/map/geocode")
def map_geocode(address: str = Query(...), city: str = Query("")):
    return geocode(address=address, city=city)


@router.get("/api/map/route")
def map_route(
    origin: str = Query(...),
    destination: str = Query(...),
    city: str = Query(""),
    mode: str = Query("transit"),
):
    return estimate_route(origin=origin, destination=destination, city=city, mode=mode)


@router.get("/api/map/static")
def map_static(
    city: str = Query(...),
    keyword: str = Query("景点"),
    limit: int = Query(6, ge=1, le=10),
    center: str = Query(""),
    zoom: int = Query(10, ge=3, le=18),
    size: str = Query("1024*420"),
    points: str = Query(""),
):
    locations = [item.strip() for item in points.split("|") if item.strip()]
    if locations:
        result = static_map_from_locations(locations=locations, center=center, zoom=zoom, size=size)
    else:
        result = static_map_from_pois(city=city, keyword=keyword, limit=limit, center=center, zoom=zoom, size=size)
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result.get("error", "AMap static map failed"))
    return Response(content=result["image"], media_type="image/png")


@router.get("/api/travel/notes")
def travel_notes(
    city: str = Query(...),
    keywords: str = Query("旅游 攻略 避坑 预约"),
    limit: int = Query(5, ge=1, le=8),
):
    return search_travel_notes(city=city, keywords=keywords, limit=limit)


@router.get("/api/poi/photo")
def poi_photo(
    name: str = Query(...),
    city: str = Query(""),
):
    """Load a real AMap POI image without a social-platform cookie."""
    result = search_poi(city=city, keyword=name, limit=5)
    for poi in result.get("pois") or []:
        photo_url = str(poi.get("photo_url") or "").strip()
        if photo_url:
            return {
                "ok": True,
                "provider": "amap_poi_photo",
                "name": name,
                "city": city,
                "photo_url": photo_url,
                "photo_urls": poi.get("photo_urls") or [photo_url],
            }
    return {"ok": False, "provider": "amap_poi_photo", "name": name, "city": city, "photo_url": "", "error": "没有找到可用的景点图片"}


@router.post("/api/trip/plan", response_model=TripPlanResponseBody)
def plan_trip(request_body: TripPlanRequestBody):
    try:
        request = _to_trip_request(request_body)
        result = execute_trip_plan(request)
        return TripPlanResponseBody(
            success=True,
            **result,
        )
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/api/trip/plan/async")
def start_trip_plan(request_body: TripPlanRequestBody):
    request = _to_trip_request(request_body)

    def worker(on_step):
        return execute_trip_plan(request, on_step=on_step)

    job_id = trip_job_store.start(worker)
    return {
        "success": True,
        "job_id": job_id,
        "status": "queued",
    }


@router.get("/api/trip/jobs/{job_id}")
def get_trip_job(job_id: str):
    try:
        job = trip_job_store.get(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Trip planning job not found") from error
    return {
        "success": job["status"] != "failed",
        **job,
    }


@router.get("/api/trip/jobs/{job_id}/graph")
def get_trip_job_graph(job_id: str):
    try:
        job = trip_job_store.get(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Trip planning job not found") from error

    graph = job.get("knowledge_graph")
    if graph is None and job.get("structured_plan"):
        graph = build_knowledge_graph(job["structured_plan"])

    return {
        "success": job["status"] == "completed" and graph is not None,
        "job_id": job_id,
        "status": job["status"],
        "knowledge_graph": graph,
        "structured_plan": job.get("structured_plan"),
    }


@router.post("/api/trip/jobs/{job_id}/cancel")
def cancel_trip_job(job_id: str):
    try:
        job = trip_job_store.cancel(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Trip planning job not found") from error
    return {
        "success": True,
        "job_id": job_id,
        "status": job["status"],
    }


@router.post("/api/cache/clear")
def clear_cache():
    clear_tool_cache()
    return {
        "success": True,
        "message": "Tool cache cleared",
    }


@router.get("/api/memory")
def get_memory():
    return {
        "success": True,
        "memory": load_user_memory(),
    }


@router.post("/api/memory")
def update_memory(memory: UserMemoryBody):
    return {
        "success": True,
        "memory": save_user_memory(_model_to_dict(memory)),
    }


@router.post("/api/memory/from-request")
def save_memory_from_request(request_body: TripPlanRequestBody):
    request = _raw_trip_request(request_body)
    return {
        "success": True,
        "memory": memory_from_request(request),
    }


@router.post("/api/memory/reset")
def reset_memory():
    return {
        "success": True,
        "memory": reset_user_memory(),
    }


def _to_trip_request(request_body: TripPlanRequestBody) -> TripPlanningRequest:
    return merge_request_with_memory(_raw_trip_request(request_body))


def _raw_trip_request(request_body: TripPlanRequestBody) -> TripPlanningRequest:
    return TripPlanningRequest(
        city=request_body.city,
        start_date=request_body.start_date,
        days=request_body.days,
        travelers=request_body.travelers,
        max_budget=request_body.max_budget,
        preferences=request_body.preferences,
        pace=request_body.pace,
        accommodation=request_body.accommodation,
        transportation=request_body.transportation,
        special_requirements=request_body.special_requirements,
        include_packing=request_body.include_packing,
        cities=request_body.cities,
    )


def _model_to_dict(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
