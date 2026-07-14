"""Packing and outfit tools for trip planning."""

from typing import Any, Dict, List

from app.core.tool import tool


@tool(description="根据天气趋势和行程活动生成行李清单与每日洋葱穿衣法建议。")
def generate_packing_and_outfits(weather_daily: List[Dict[str, Any]], itinerary_days: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate a checklist and daily layering calendar."""
    checklist = {
        "documents": ["身份证/护照", "学生证或优惠证件", "酒店与交通订单截图"],
        "electronics": ["手机", "充电器", "充电宝", "耳机"],
        "health": ["常用药", "创可贴", "纸巾/湿巾"],
        "clothes": [],
        "activity_specific": [],
    }
    outfit_calendar = []
    weather_alerts = []

    all_text = " ".join(str(day) for day in itinerary_days)
    if any(keyword in all_text for keyword in ["山", "徒步", "爬山", "郊野", "长城"]):
        checklist["activity_specific"].extend(["防滑运动鞋", "速干袜", "轻量背包"])
    if any(keyword in all_text for keyword in ["米其林", "高端餐厅", "正式"]):
        checklist["activity_specific"].extend(["简洁正装/衬衫", "干净皮鞋或通勤鞋"])
    if any(keyword in all_text for keyword in ["海边", "水上", "温泉"]):
        checklist["activity_specific"].extend(["泳衣", "防水袋", "拖鞋"])

    total_days = max(len(weather_daily), len(itinerary_days), 1)
    for index in range(1, total_days + 1):
        weather = weather_daily[index - 1] if index - 1 < len(weather_daily) else {}
        temp_max = _to_float(weather.get("temp_max", weather.get("temp_high")))
        temp_min = _to_float(weather.get("temp_min", weather.get("temp_low")))
        temp_known = _has_temperature(weather)
        desc = str(weather.get("day_weather") or weather.get("condition") or "")
        day_plan = itinerary_days[index - 1] if index - 1 < len(itinerary_days) else {}
        attractions = day_plan.get("attractions") or []
        activities = " ".join(item.get("name", "") for item in attractions)

        layers = _layers_for_temperature(temp_min, temp_max) if temp_known else ["透气上衣", "备用薄外套"]
        extras = []
        notes = []
        risk_tags = []
        wind_speed = _to_float(weather.get("wind_scale"))
        has_rain = any(word in desc for word in ["雨", "阵雨", "雷", "storm", "shower"])
        if has_rain:
            extras.append("轻便雨衣")
            checklist["clothes"].append("轻便雨衣")
            checklist["electronics"].append("防水手机袋")
            risk_tags.append("降雨")
            if wind_speed >= 8:
                notes.append("风偏大,优先带雨衣,不建议依赖雨伞")
            else:
                notes.append("带折叠伞或轻便雨衣,鞋子选防滑鞋底")
        if any(word in activities for word in ["山", "徒步", "爬山", "郊野", "长城"]):
            extras.append("防滑运动鞋")
            checklist["activity_specific"].extend(["防滑运动鞋", "轻量背包"])
            notes.append("当天有户外步行强度,鞋比衣服更关键")
        if temp_known and temp_max >= 30:
            extras.append("遮阳帽/防晒")
            checklist["health"].append("防晒霜")
            checklist["health"].append("电解质水/补盐片")
            risk_tags.append("高温")
            notes.append("中午减少暴晒,补水频率提高")
        if temp_known and temp_min <= 8:
            checklist["clothes"].append("保暖外套")
            risk_tags.append("低温")
            notes.append("早晚温差明显,外层要能挡风")
        if wind_speed >= 10:
            checklist["clothes"].append("防风外套")
            risk_tags.append("大风")
            notes.append("外套优先防风,帽子选择可固定款")
        if not desc and not weather_daily:
            notes.append("未接入天气数据,按常规城市出行准备备用外套")

        outfit_calendar.append({
            "day": index,
            "date": weather.get("date"),
            "weather": desc or "天气待确认",
            "temperature": _temperature_text(temp_min, temp_max, temp_known),
            "layers": layers,
            "extras": extras,
            "outfit": " + ".join(layers + extras),
            "activity_hint": _activity_hint(attractions),
            "risk_tags": risk_tags,
            "notes": notes,
        })
        if risk_tags:
            weather_alerts.append({
                "day": index,
                "tags": risk_tags,
                "message": "、".join(notes) if notes else "当天存在天气风险,建议预留调整空间",
            })

    checklist["clothes"].extend(["换洗内衣袜", "睡衣", "备用上衣"])
    checklist = {key: _dedupe(items) for key, items in checklist.items()}

    return {
        "ok": True,
        "checklist": checklist,
        "onion_layering_calendar": outfit_calendar,
        "weather_alerts": weather_alerts,
    }


def _layers_for_temperature(temp_min: float, temp_max: float) -> List[str]:
    if temp_max == 0 and temp_min == 0:
        return ["透气上衣", "备用薄外套"]
    if temp_max >= 28:
        return ["短袖", "轻薄外套"]
    if temp_max >= 20:
        return ["短袖/薄长袖", "薄外套"]
    if temp_max >= 12:
        return ["长袖", "针织衫/卫衣", "薄外套"]
    return ["保暖内搭", "毛衣/抓绒", "厚外套"]


def _temperature_text(temp_min: float, temp_max: float, temp_known: bool) -> str:
    if not temp_known:
        return "待确认"
    return f"{temp_min:g}-{temp_max:g}℃"


def _has_temperature(weather: Dict[str, Any]) -> bool:
    return weather.get("temp_max", weather.get("temp_high")) is not None and weather.get("temp_min", weather.get("temp_low")) is not None


def _activity_hint(attractions: List[Dict[str, Any]]) -> str:
    names = "、".join(item.get("name", "") for item in attractions if item.get("name"))
    if not names:
        return "常规城市游览"
    if any(word in names for word in ["山", "徒步", "长城", "郊野"]):
        return "户外步行强度较高"
    if any(word in names for word in ["博物馆", "美术馆", "展览"]):
        return "室内场馆为主,注意空调温差"
    if any(word in names for word in ["餐厅", "米其林", "酒店"]):
        return "餐饮住宿场景,穿搭保持整洁"
    return "城市步行与观光"


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _dedupe(items: List[str]) -> List[str]:
    result = []
    seen = set()
    for item in items:
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    return result
