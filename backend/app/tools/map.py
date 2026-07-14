"""AMap tools for POI, geocoding and route estimation."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.tool import tool
from app.runtime_settings import load_backend_env


AMAP_HOST = "https://restapi.amap.com/v3"
AMAP_REQUEST_TIMEOUT_SECONDS = 8
AMAP_ROUTE_TIMEOUT_SECONDS = 6


@tool(description="使用高德地图搜索真实POI。返回名称、地址、类型、经纬度和POI ID。")
def search_poi(city: str, keyword: str, limit: int = 8) -> Dict[str, Any]:
    """Search AMap POIs by city and keyword."""
    api_key = _amap_key()
    if not api_key:
        return {"ok": False, "error": "AMAP_WEB_SERVICE_KEY or AMAP_API_KEY is not configured"}

    clean_keyword = keyword.strip() if keyword else "景点"
    try:
        data = _amap_get("/place/text", {
            "key": api_key,
            "keywords": clean_keyword,
            "city": city,
            "citylimit": "true",
            "extensions": "all",
            "offset": max(1, min(limit, 25)),
            "page": 1,
        })
        pois = []
        for item in (data.get("pois") or [])[:limit]:
            lng, lat = _split_location(item.get("location"))
            pois.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "type": item.get("type"),
                "address": _normalize_address(item.get("address")),
                "location": {"longitude": lng, "latitude": lat},
                "rating": _extract_deep(item, ["biz_ext", "rating"]),
                "cost": _extract_deep(item, ["biz_ext", "cost"]),
                "photo_url": _first_photo_url(item.get("photos")),
                "photo_urls": _photo_urls(item.get("photos")),
            })
        return {"ok": True, "provider": "amap", "city": city, "keyword": clean_keyword, "pois": pois}
    except (HTTPError, URLError, RuntimeError) as error:
        return {"ok": False, "error": str(error)}


@tool(description="使用高德地图把地址转换为经纬度。")
def geocode(address: str, city: str = "") -> Dict[str, Any]:
    """Geocode an address with AMap."""
    api_key = _amap_key()
    if not api_key:
        return {"ok": False, "error": "AMAP_WEB_SERVICE_KEY or AMAP_API_KEY is not configured"}

    params = {"key": api_key, "address": address}
    if city:
        params["city"] = city

    try:
        data = _amap_get("/geocode/geo", params)
        geocodes = data.get("geocodes") or []
        if not geocodes:
            return {"ok": False, "error": f"No geocode result for {address}"}
        item = geocodes[0]
        lng, lat = _split_location(item.get("location"))
        return {
            "ok": True,
            "formatted_address": item.get("formatted_address"),
            "province": item.get("province"),
            "city": item.get("city"),
            "district": item.get("district"),
            "location": {"longitude": lng, "latitude": lat},
        }
    except (HTTPError, URLError, RuntimeError) as error:
        return {"ok": False, "error": str(error)}


@tool(description="估算两个地点之间的路线距离和耗时。mode支持walking/driving/transit。")
def estimate_route(
    origin: str,
    destination: str,
    city: str = "",
    mode: str = "transit",
) -> Dict[str, Any]:
    """Estimate route distance and duration using AMap."""
    api_key = _amap_key()
    if not api_key:
        return {"ok": False, "error": "AMAP_WEB_SERVICE_KEY or AMAP_API_KEY is not configured"}

    origin_loc = origin if _is_location_string(origin) else ""
    destination_loc = destination if _is_location_string(destination) else ""
    if not origin_loc:
        origin_geo = geocode(origin, city)
        if not origin_geo.get("ok"):
            return {"ok": False, "error": f"origin geocode failed: {origin_geo.get('error')}"}
        origin_loc = _format_location(origin_geo["location"])
    if not destination_loc:
        destination_geo = geocode(destination, city)
        if not destination_geo.get("ok"):
            return {"ok": False, "error": f"destination geocode failed: {destination_geo.get('error')}"}
        destination_loc = _format_location(destination_geo["location"])
    route_mode = mode.lower()

    try:
        if route_mode == "walking":
            route = _walking_route(api_key, origin_loc, destination_loc)
        elif route_mode == "driving":
            route = _driving_route(api_key, origin_loc, destination_loc)
        else:
            route = _transit_route(api_key, origin_loc, destination_loc, city)

        route.update({
            "ok": True,
            "provider": "amap",
            "mode": route_mode,
            "origin": origin,
            "destination": destination,
        })
        return route
    except (HTTPError, URLError, RuntimeError) as error:
        return {"ok": False, "error": str(error), "origin": origin, "destination": destination}


def fetch_static_map(
    center: str,
    markers: str = "",
    size: str = "1024*420",
    zoom: int = 12,
) -> bytes:
    """Fetch an AMap static map image through the backend key."""
    api_key = _amap_key()
    if not api_key:
        raise RuntimeError("AMAP_WEB_SERVICE_KEY or AMAP_API_KEY is not configured")

    params: Dict[str, Any] = {
        "key": api_key,
        "location": center,
        "zoom": max(3, min(int(zoom), 18)),
        "size": size,
    }
    if markers:
        params["markers"] = markers

    signed_params = _with_signature(params)
    url = f"{AMAP_HOST}/staticmap?{urlencode(signed_params)}"
    with urlopen(Request(url), timeout=20) as response:
        return response.read()


def static_map_from_pois(
    city: str,
    keyword: str,
    limit: int = 6,
    center: str = "",
    zoom: int = 10,
    size: str = "1024*420",
) -> Dict[str, Any]:
    """Search POIs and return image bytes plus POI metadata for map display."""
    result = search_poi(city=city, keyword=keyword, limit=limit)
    if not result.get("ok"):
        return result

    pois = [
        poi for poi in result.get("pois", [])
        if poi.get("location", {}).get("longitude") and poi.get("location", {}).get("latitude")
    ]
    if not pois:
        return {"ok": False, "error": "No POI coordinates available"}

    map_center = center if _is_location_string(center) else _average_center(pois)
    markers = "|".join(
        f"mid,,{index + 1}:{poi['location']['longitude']},{poi['location']['latitude']}"
        for index, poi in enumerate(pois[:10])
    )
    return {
        "ok": True,
        "provider": "amap",
        "center": map_center,
        "zoom": max(3, min(int(zoom), 18)),
        "pois": pois,
        "image": fetch_static_map(center=map_center, markers=markers, size=size, zoom=zoom),
    }


def static_map_from_locations(
    locations: List[str],
    center: str = "",
    zoom: int = 10,
    size: str = "1024*420",
) -> Dict[str, Any]:
    """Render a static map from already-resolved POI coordinates."""
    valid_locations = [item for item in locations if _is_location_string(item)]
    if not valid_locations:
        return {"ok": False, "error": "No valid map locations available"}

    pois = [
        {
            "location": {
                "longitude": item.split(",", 1)[0],
                "latitude": item.split(",", 1)[1],
            }
        }
        for item in valid_locations
    ]
    map_center = center if _is_location_string(center) else _average_center(pois)
    markers = "|".join(f"mid,,{index + 1}:{location}" for index, location in enumerate(valid_locations[:20]))
    return {
        "ok": True,
        "provider": "amap",
        "center": map_center,
        "zoom": max(3, min(int(zoom), 18)),
        "locations": valid_locations,
        "image": fetch_static_map(center=map_center, markers=markers, size=size, zoom=zoom),
    }


def _average_center(pois: List[Dict[str, Any]]) -> str:
    lngs = [float(poi["location"]["longitude"]) for poi in pois if poi.get("location", {}).get("longitude") is not None]
    lats = [float(poi["location"]["latitude"]) for poi in pois if poi.get("location", {}).get("latitude") is not None]
    if not lngs or not lats:
        first_location = pois[0]["location"]
        return f"{first_location['longitude']},{first_location['latitude']}"
    return f"{sum(lngs) / len(lngs):.6f},{sum(lats) / len(lats):.6f}"


def _walking_route(api_key: str, origin: str, destination: str) -> Dict[str, Any]:
    data = _amap_get("/direction/walking", {
        "key": api_key,
        "origin": origin,
        "destination": destination,
    }, timeout=AMAP_ROUTE_TIMEOUT_SECONDS)
    paths = data.get("route", {}).get("paths") or []
    if not paths:
        raise RuntimeError("No walking route found")
    path = paths[0]
    return _route_result(path.get("distance"), path.get("duration"), "walking")


def _driving_route(api_key: str, origin: str, destination: str) -> Dict[str, Any]:
    data = _amap_get("/direction/driving", {
        "key": api_key,
        "origin": origin,
        "destination": destination,
        "extensions": "base",
    }, timeout=AMAP_ROUTE_TIMEOUT_SECONDS)
    paths = data.get("route", {}).get("paths") or []
    if not paths:
        raise RuntimeError("No driving route found")
    path = paths[0]
    return _route_result(path.get("distance"), path.get("duration"), "driving")


def _transit_route(api_key: str, origin: str, destination: str, city: str) -> Dict[str, Any]:
    data = _amap_get("/direction/transit/integrated", {
        "key": api_key,
        "origin": origin,
        "destination": destination,
        "city": city,
        "cityd": city,
    }, timeout=AMAP_ROUTE_TIMEOUT_SECONDS)
    transits = data.get("route", {}).get("transits") or []
    if not transits:
        raise RuntimeError("No transit route found")
    transit = transits[0]
    return _route_result(transit.get("distance"), transit.get("duration"), "transit")


def _route_result(distance: Any, duration: Any, mode: str) -> Dict[str, Any]:
    distance_m = _to_float(distance)
    duration_s = _to_float(duration)
    return {
        "distance_meters": round(distance_m, 1),
        "duration_minutes": round(duration_s / 60, 1),
        "mode_used": mode,
    }


def _amap_get(path: str, params: Dict[str, Any], timeout: int = AMAP_REQUEST_TIMEOUT_SECONDS) -> Dict[str, Any]:
    signed_params = _with_signature(params)
    url = f"{AMAP_HOST}{path}?{urlencode(signed_params)}"
    with urlopen(Request(url), timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    if str(data.get("status")) != "1":
        raise RuntimeError(_format_amap_error(data))
    return data


def _format_amap_error(data: Dict[str, Any]) -> str:
    info_code = str(data.get("infocode") or "")
    info = str(data.get("info") or "UNKNOWN")
    hints = {
        "10001": "请检查 AMAP_WEB_SERVICE_KEY 是否填写正确。",
        "10003": "高德接口访问量已达上限,需要检查配额或稍后重试。",
        "10005": "当前服务器公网出口 IP 不在该 key 的 IP 白名单中。",
        "10007": "当前 key 开启了数字签名校验。请关闭数字签名,或在 AMAP_SIG_PRIVATE_KEY 中配置该 key 对应的签名私钥。",
        "10009": "当前 key 不是 Web服务 API key,或 Web服务 key 绑定的 IP 白名单不包含当前公网出口 IP。",
        "10010": "请检查高德控制台中该 key 启用的服务类型。",
    }
    hint = hints.get(info_code)
    if hint:
        return f"AMap error {info_code}: {info}. {hint}"
    return f"AMap error {info_code}: {info}"


def _amap_key() -> str:
    env = _read_backend_env()
    return _env_value(env, "AMAP_WEB_SERVICE_KEY") or _env_value(env, "AMAP_API_KEY")


def _with_signature(params: Dict[str, Any]) -> Dict[str, Any]:
    env = _read_backend_env()
    private_key = _env_value(env, "AMAP_SIG_PRIVATE_KEY") or _env_value(env, "AMAP_PRIVATE_KEY")
    if not private_key:
        return params

    signed_params = dict(params)
    query = "&".join(
        f"{key}={signed_params[key]}"
        for key in sorted(signed_params)
        if signed_params[key] is not None
    )
    raw_signature = f"{query}{private_key}"
    signed_params["sig"] = hashlib.md5(raw_signature.encode("utf-8")).hexdigest()
    return signed_params


def _read_backend_env() -> Dict[str, str]:
    return load_backend_env()


def _env_value(file_env: Dict[str, str], key: str) -> str:
    return os.getenv(key) or file_env.get(key, "")


def _split_location(value: Optional[str]) -> tuple:
    if not value or "," not in value:
        return None, None
    lng, lat = value.split(",", 1)
    return _to_float(lng), _to_float(lat)


def _format_location(location: Dict[str, Any]) -> str:
    return f"{location.get('longitude')},{location.get('latitude')}"


def _is_location_string(value: str) -> bool:
    if not value or "," not in value:
        return False
    lng, lat = value.split(",", 1)
    try:
        lng_value = float(lng)
        lat_value = float(lat)
    except ValueError:
        return False
    return -180 <= lng_value <= 180 and -90 <= lat_value <= 90


def _normalize_address(value: Any) -> str:
    if isinstance(value, list):
        return ""
    return str(value or "")


def _extract_deep(data: Dict[str, Any], keys: List[str]) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _photo_urls(photos: Any) -> List[str]:
    if not isinstance(photos, list):
        return []
    urls: List[str] = []
    for photo in photos:
        if not isinstance(photo, dict):
            continue
        url = str(photo.get("url") or "").strip()
        if url and url not in urls:
            urls.append(url)
    return urls[:5]


def _first_photo_url(photos: Any) -> str:
    urls = _photo_urls(photos)
    return urls[0] if urls else ""


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
