"""Public travel research through Tavily, without platform cookies."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.llm import OpenAICompatibleLLM
from app.core.tool import tool
from app.core.types import ChatMessage
from app.runtime_settings import load_backend_env


TAVILY_TIMEOUT_SECONDS = 12
_ATTRACTION_SUFFIXES = (
    "景区", "公园", "博物馆", "古镇", "古城", "纪念馆", "故居", "遗址",
    "寺", "塔", "动物园", "植物园", "长城", "广场", "步行街", "山", "湖", "岛",
)
_BLOCKED_WORDS = (
    "便利店", "超市", "餐厅", "酒店", "宾馆", "停车场", "医院", "银行", "药店",
    "加油站", "洗车", "维修", "门票售卖处", "游客中心",
)


@tool(description="通过Tavily搜索公开旅行攻略,提炼候选景点、避坑点和预约提醒,再由高德POI确认景点真实性。")
def search_travel_notes(city: str, keywords: str = "", limit: int = 5) -> Dict[str, Any]:
    """Search public travel pages and return structured travel insights."""
    env = load_backend_env()
    api_key = env.get("TAVILY_API_KEY", "").strip()
    query = f"{city.strip()} {keywords.strip() or '旅游景点 攻略 避坑 预约'}"
    safe_limit = max(1, min(int(limit or 5), 8))
    if not api_key:
        return _failed_result(query, "TAVILY_API_KEY is not configured")

    payload: Dict[str, Any] = {
        "api_key": api_key,
        "query": query,
        "topic": "general",
        "search_depth": "advanced",
        "max_results": safe_limit,
        "include_answer": False,
        "include_raw_content": True,
    }
    domains = [item.strip() for item in env.get("TAVILY_INCLUDE_DOMAINS", "").split(",") if item.strip()]
    if domains:
        payload["include_domains"] = domains

    try:
        data = _tavily_search(env.get("TAVILY_API_HOST", "https://api.tavily.com"), payload)
    except (HTTPError, URLError, RuntimeError, ValueError) as error:
        return _failed_result(query, f"Tavily search failed: {error}")

    notes = []
    for item in (data.get("results") or [])[:safe_limit]:
        title = str(item.get("title") or "公开旅行攻略").strip()
        url = str(item.get("url") or "").strip()
        content = str(item.get("raw_content") or item.get("content") or "").strip()
        if not url and not content:
            continue
        notes.append({
            "title": title,
            "url": url,
            "summary": _compact_text(str(item.get("content") or content), 220),
            "candidate_attractions": _extract_attractions(title + " " + content),
            "pitfalls": _extract_sentences(content, ("避坑", "不要", "排队", "人多", "关闭", "限流")),
            "reservation_tips": _extract_sentences(content, ("预约", "提前", "门票", "实名", "放票", "预约码")),
            "source": "tavily",
        })

    if not notes:
        return _failed_result(query, "Tavily returned no usable public travel pages")

    insights = _extract_insights_with_llm(city, notes)
    if not insights["candidate_attractions"]:
        insights["candidate_attractions"] = _unique(
            item for note in notes for item in note["candidate_attractions"]
        )[:10]
    if not insights["pitfalls"]:
        insights["pitfalls"] = _unique(item for note in notes for item in note["pitfalls"])[:10]
    if not insights["reservation_tips"]:
        insights["reservation_tips"] = _unique(item for note in notes for item in note["reservation_tips"])[:10]

    return {
        "ok": True,
        "provider": "tavily",
        "query": query,
        "notes": notes,
        "merged_insights": insights,
        "fallback_hint": "",
    }


def _tavily_search(host: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = host.rstrip("/") + "/search"
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=TAVILY_TIMEOUT_SECONDS) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Tavily response is not an object")
    return data


def _extract_insights_with_llm(city: str, notes: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    source = "\n\n".join(
        f"Source {index + 1}\nTitle: {note['title']}\nContent: {note['summary']}"
        for index, note in enumerate(notes)
    )
    prompt = f"""You extract factual travel information for {city} from public web pages.
Return JSON only with exactly these arrays:
{{"candidate_attractions":[],"pitfalls":[],"reservation_tips":[]}}
Only include facts supported by the sources. Candidate attractions must be formal place names,
not restaurants, hotels, convenience stores, shopping malls, or transport facilities.
Deduplicate each array and return at most 10 items.

{source}"""
    try:
        content = OpenAICompatibleLLM.from_env().chat(
            [ChatMessage(role="user", content=prompt)],
            temperature=0.1,
        )
        parsed = _parse_json_object(content)
        return {
            "candidate_attractions": _clean_list(parsed.get("candidate_attractions")),
            "pitfalls": _clean_list(parsed.get("pitfalls")),
            "reservation_tips": _clean_list(parsed.get("reservation_tips")),
        }
    except Exception:
        return {"candidate_attractions": [], "pitfalls": [], "reservation_tips": []}


def _extract_attractions(text: str) -> List[str]:
    result = []
    for suffix in _ATTRACTION_SUFFIXES:
        for match in re.finditer(rf"[\u4e00-\u9fffA-Za-z0-9·]{{2,18}}{re.escape(suffix)}", text):
            value = match.group(0).strip(" ，,。.!！?？:：;；()（）")
            if value and not any(word in value for word in _BLOCKED_WORDS) and value not in result:
                result.append(value)
    return result[:10]


def _extract_sentences(text: str, keywords: tuple[str, ...]) -> List[str]:
    result = []
    for sentence in re.split(r"[。！？!?\n]", text):
        clean = _compact_text(sentence, 120)
        if clean and any(keyword in clean for keyword in keywords) and clean not in result:
            result.append(clean)
    return result[:10]


def _parse_json_object(content: str) -> Dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I | re.S)
    match = re.search(r"\{.*\}", cleaned, flags=re.S)
    return json.loads(match.group(0) if match else cleaned)


def _clean_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return _unique(_compact_text(str(item), 120) for item in value)[:10]


def _unique(items) -> List[str]:
    result = []
    for item in items:
        value = str(item or "").strip()
        if value and value not in result:
            result.append(value)
    return result


def _compact_text(value: str, limit: int) -> str:
    return re.sub(r"\s+", " ", value).strip()[:limit]


def _failed_result(query: str, error: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "provider": "tavily",
        "query": query,
        "notes": [],
        "merged_insights": {"candidate_attractions": [], "pitfalls": [], "reservation_tips": []},
        "error": error,
        "fallback_hint": "规划会继续使用高德 POI,请在设置中配置 Tavily API Key 后重试。",
    }
