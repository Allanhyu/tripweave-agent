"""Weather tools for the handwritten Agent."""

import gzip
import json
import os
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.tool import tool
from app.tools.map import geocode
from app.runtime_settings import load_backend_env


OPENWEATHER_TIMEOUT_SECONDS = 6


@tool(description="查询城市未来若干天的天气预报。使用OpenWeather 5天/3小时预报并按日期聚合。")
def get_weather_forecast(city: str, days: int = 3, start_date: str = "") -> Dict[str, Any]:
    """Query OpenWeather forecast by city name and aggregate it by day."""
    env = _read_backend_env()
    api_key = _env_value(env, "OPENWEATHER_API_KEY")
    api_host = _env_value(env, "OPENWEATHER_API_HOST") or "https://api.openweathermap.org"
    api_host = api_host.rstrip("/")

    if not api_key:
        return {"ok": False, "error": "OPENWEATHER_API_KEY is not configured"}

    safe_days = max(1, min(days, 5))
    query_city = _normalize_openweather_city(city)
    coordinates = _resolve_chinese_city_coordinates(city)
    try:
        forecast_params = {
            "appid": api_key,
            "units": "metric",
            "lang": "zh_cn",
        }
        if coordinates:
            forecast_params.update({"lat": coordinates[1], "lon": coordinates[0]})
        else:
            forecast_params["q"] = query_city
        data = _openweather_get(api_host, "/data/2.5/forecast", forecast_params)
        daily = _aggregate_daily(data.get("list") or [], safe_days, start_date)
        if not daily:
            available_dates = sorted({
                str(item.get("dt_txt") or "").split(" ")[0]
                for item in data.get("list") or []
                if item.get("dt_txt")
            })
            return {
                "ok": False,
                "provider": "openweather",
                "requested_city": city,
                "query_city": query_city,
                "resolved_location": coordinates,
                "city": (data.get("city") or {}).get("name", city),
                "country": (data.get("city") or {}).get("country"),
                "daily": [],
                "error": "出发日期超出 OpenWeather 当前 5 天预报窗口",
                "available_from": available_dates[0] if available_dates else "",
                "available_until": available_dates[-1] if available_dates else "",
            }
        return {
            "ok": True,
            "provider": "openweather",
            "requested_city": city,
            "query_city": query_city,
            "resolved_location": coordinates,
            "city": (data.get("city") or {}).get("name", city),
            "country": (data.get("city") or {}).get("country"),
            "daily": daily,
        }
    except HTTPError as error:
        return {
            "ok": False,
            "error": f"OpenWeather HTTP {error.code}",
            "detail": _decode_body(error.read()),
        }
    except URLError as error:
        return {"ok": False, "error": f"OpenWeather connection failed: {error.reason}"}
    except RuntimeError as error:
        return {"ok": False, "error": str(error)}


def _normalize_openweather_city(city: str) -> str:
    clean_city = city.strip()
    if "," in clean_city:
        return clean_city

    if clean_city.endswith("市"):
        clean_city = clean_city[:-1]

    aliases = {
        "北京": "Beijing,CN",
        "北京市": "Beijing,CN",
        "上海": "Shanghai,CN",
        "上海市": "Shanghai,CN",
        "广州": "Guangzhou,CN",
        "广州市": "Guangzhou,CN",
        "深圳": "Shenzhen,CN",
        "深圳市": "Shenzhen,CN",
        "杭州": "Hangzhou,CN",
        "杭州市": "Hangzhou,CN",
        "南京": "Nanjing,CN",
        "南京市": "Nanjing,CN",
        "成都": "Chengdu,CN",
        "成都市": "Chengdu,CN",
        "重庆": "Chongqing,CN",
        "重庆市": "Chongqing,CN",
        "西安": "Xi'an,CN",
        "西安市": "Xi'an,CN",
        "武汉": "Wuhan,CN",
        "武汉市": "Wuhan,CN",
        "苏州": "Suzhou,CN",
        "苏州市": "Suzhou,CN",
        "厦门": "Xiamen,CN",
        "厦门市": "Xiamen,CN",
        "青岛": "Qingdao,CN",
        "青海": "Qinghai",
        "青海省": "Qinghai",
        "合肥": "Hefei,CN",
        "安庆": "Anqing,CN",
        "芜湖": "Wuhu,CN",
        "蚌埠": "Bengbu,CN",
        "黄山": "Huangshan,CN",
    }
    if clean_city in aliases:
        return aliases[clean_city]
    if clean_city and all("\u4e00" <= char <= "\u9fff" for char in clean_city):
        return f"{clean_city},CN"
    return clean_city


def _resolve_chinese_city_coordinates(city: str) -> Optional[tuple[float, float]]:
    """Resolve Chinese regions through AMap instead of a hand-maintained alias list."""
    clean_city = str(city or "").strip()
    if not clean_city or not any("\u4e00" <= char <= "\u9fff" for char in clean_city):
        return None
    try:
        result = geocode(clean_city)
    except Exception:
        return None
    if not result.get("ok"):
        return None
    location = result.get("location") or {}
    try:
        longitude = float(location.get("longitude"))
        latitude = float(location.get("latitude"))
    except (TypeError, ValueError):
        return None
    if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
        return None
    return longitude, latitude


def _openweather_get(api_host: str, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{api_host}{path}?{urlencode(params)}"
    request = Request(url, headers={"Accept-Encoding": "gzip"})
    with urlopen(request, timeout=OPENWEATHER_TIMEOUT_SECONDS) as response:
        data = json.loads(_decode_body(response.read()))

    if str(data.get("cod")) != "200":
        raise RuntimeError(f"OpenWeather cod={data.get('cod')}: {data}")
    return data


def _aggregate_daily(items: List[Dict[str, Any]], days: int, start_date: str = "") -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in items:
        dt_txt = item.get("dt_txt") or ""
        date = dt_txt.split(" ")[0]
        if date:
            grouped[date].append(item)

    daily = []
    start = _parse_date(start_date)
    candidate_dates = []
    for date_text in sorted(grouped.keys()):
        parsed = _parse_date(date_text)
        if start and parsed and parsed < start:
            continue
        candidate_dates.append(date_text)

    for date_text in candidate_dates[:days]:
        day_items = grouped[date_text]
        temps_min = [_to_float(item.get("main", {}).get("temp_min")) for item in day_items]
        temps_max = [_to_float(item.get("main", {}).get("temp_max")) for item in day_items]
        winds = [_to_float(item.get("wind", {}).get("speed")) for item in day_items]
        weather_texts = []
        for item in day_items:
            weather = item.get("weather") or []
            if weather:
                weather_texts.append(weather[0].get("description") or weather[0].get("main") or "")
        dominant_weather = Counter([text for text in weather_texts if text]).most_common(1)

        daily.append({
            "date": date_text,
            "day_weather": dominant_weather[0][0] if dominant_weather else "",
            "night_weather": dominant_weather[0][0] if dominant_weather else "",
            "temp_max": round(max(temps_max), 1) if temps_max else 0,
            "temp_min": round(min(temps_min), 1) if temps_min else 0,
            "wind_direction": "",
            "wind_scale": round(max(winds), 1) if winds else 0,
            "source_points": len(day_items),
        })
    return daily


def _parse_date(value: str) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _decode_body(raw: bytes) -> str:
    try:
        raw = gzip.decompress(raw)
    except Exception:
        pass
    return raw.decode("utf-8", errors="replace")


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _read_backend_env() -> Dict[str, str]:
    return load_backend_env()


def _env_value(file_env: Dict[str, str], key: str) -> str:
    return os.getenv(key) or file_env.get(key, "")
