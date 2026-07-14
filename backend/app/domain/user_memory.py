"""Long-term user preference memory stored in a local JSON file."""

import json
import threading
from pathlib import Path
from typing import Any, Dict, List

from app.domain.schemas import TripPlanningRequest


DEFAULT_MEMORY: Dict[str, Any] = {
    "default_city": "",
    "travelers": 1,
    "max_budget": 0,
    "preferences": [],
    "avoid": [],
    "pace": "moderate",
    "accommodation": "standard hotel",
    "transportation": "public transit",
    "include_packing": True,
}

_MEMORY_PATH = Path(__file__).resolve().parents[2] / "data" / "user_memory.json"
_LOCK = threading.Lock()


def load_user_memory() -> Dict[str, Any]:
    with _LOCK:
        _ensure_memory_file()
        return json.loads(_MEMORY_PATH.read_text(encoding="utf-8"))


def save_user_memory(memory: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _normalize_memory(memory)
    with _LOCK:
        _MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        _MEMORY_PATH.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return normalized


def reset_user_memory() -> Dict[str, Any]:
    return save_user_memory(DEFAULT_MEMORY)


def merge_request_with_memory(request: TripPlanningRequest) -> TripPlanningRequest:
    memory = load_user_memory()
    # An empty list from the form means the user intentionally removed all preferences.
    preferences = list(request.preferences or [])
    avoid = list(memory.get("avoid") or [])
    special_requirements = request.special_requirements.strip()
    if avoid:
        avoid_text = "避免: " + ", ".join(avoid)
        special_requirements = f"{special_requirements}; {avoid_text}" if special_requirements else avoid_text

    return TripPlanningRequest(
        city=request.city or str(memory.get("default_city") or ""),
        start_date=request.start_date,
        days=request.days,
        cities=list(request.cities or []),
        travelers=request.travelers or int(memory.get("travelers") or 1),
        max_budget=request.max_budget or float(memory.get("max_budget") or 0),
        preferences=preferences,
        pace=request.pace or str(memory.get("pace") or "moderate"),
        accommodation=request.accommodation or str(memory.get("accommodation") or "standard hotel"),
        transportation=request.transportation or str(memory.get("transportation") or "public transit"),
        special_requirements=special_requirements,
        include_packing=request.include_packing if request.include_packing is not None else bool(memory.get("include_packing", True)),
    )


def memory_from_request(request: TripPlanningRequest) -> Dict[str, Any]:
    avoid = []
    lower_requirements = request.special_requirements.lower()
    if "太赶" in request.special_requirements or "赶" in lower_requirements:
        avoid.append("太赶")
    if "少走回头路" in request.special_requirements:
        avoid.append("走回头路")

    return save_user_memory({
        "default_city": request.city,
        "travelers": request.travelers,
        "max_budget": request.max_budget,
        "preferences": request.preferences,
        "avoid": avoid,
        "pace": request.pace,
        "accommodation": request.accommodation,
        "transportation": request.transportation,
        "include_packing": request.include_packing,
    })


def _ensure_memory_file() -> None:
    if not _MEMORY_PATH.exists():
        reset_user_memory()


def _normalize_memory(memory: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "default_city": str(memory.get("default_city") or DEFAULT_MEMORY["default_city"]),
        "travelers": _to_int(memory.get("travelers"), DEFAULT_MEMORY["travelers"]),
        "max_budget": _to_float(memory.get("max_budget"), DEFAULT_MEMORY["max_budget"]),
        "preferences": _string_list(memory.get("preferences")),
        "avoid": _string_list(memory.get("avoid")),
        "pace": str(memory.get("pace") or DEFAULT_MEMORY["pace"]),
        "accommodation": str(memory.get("accommodation") or DEFAULT_MEMORY["accommodation"]),
        "transportation": str(memory.get("transportation") or DEFAULT_MEMORY["transportation"]),
        "include_packing": bool(memory.get("include_packing", DEFAULT_MEMORY["include_packing"])),
    }


def _string_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
