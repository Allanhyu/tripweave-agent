"""Runtime configuration shared by the local settings panel and tools."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ROOT_ENV_PATH = PROJECT_ROOT / ".env"
ENV_PATH = BACKEND_ROOT / ".env"
RUNTIME_SETTINGS_PATH = BACKEND_ROOT / "runtime_settings.json"

RUNTIME_KEYS = {
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL_ID",
    "LLM_TIMEOUT",
    "LLM_RESPONSE_FORMAT",
    "AMAP_WEB_SERVICE_KEY",
    "AMAP_WEB_JS_KEY",
    "AMAP_SECURITY_JS_CODE",
    "OPENWEATHER_API_KEY",
    "OPENWEATHER_API_HOST",
    "TAVILY_API_KEY",
    "TAVILY_API_HOST",
    "TAVILY_INCLUDE_DOMAINS",
}


def _parse_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_runtime_settings() -> Dict[str, str]:
    if not RUNTIME_SETTINGS_PATH.exists():
        return {}
    try:
        data = json.loads(RUNTIME_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {
        key: str(value)
        for key, value in (data.items() if isinstance(data, dict) else [])
        if key in RUNTIME_KEYS and value is not None
    }


def load_backend_env() -> Dict[str, str]:
    """Load root/backend env files, local UI overrides, then process env."""
    values = _parse_env_file(ROOT_ENV_PATH)
    values.update(_parse_env_file(ENV_PATH))
    values.update(load_runtime_settings())
    for key in RUNTIME_KEYS:
        if os.getenv(key):
            values[key] = os.environ[key]
    return values


def save_runtime_settings(updates: Dict[str, Any]) -> Dict[str, str]:
    current = load_runtime_settings()
    for key, value in updates.items():
        if key not in RUNTIME_KEYS:
            continue
        text = str(value or "").strip()
        if text:
            current[key] = text
    RUNTIME_SETTINGS_PATH.write_text(
        json.dumps(current, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return current


def setting_status(env: Dict[str, str]) -> Dict[str, Any]:
    return {
        "llm_base_url": env.get("LLM_BASE_URL", ""),
        "llm_model": env.get("LLM_MODEL_ID", ""),
        "openweather_api_host": env.get("OPENWEATHER_API_HOST", ""),
        "amap_web_js_key": env.get("AMAP_WEB_JS_KEY", ""),
        "has_llm_api_key": bool(env.get("LLM_API_KEY") or env.get("OPENAI_API_KEY")),
        "has_amap_service_key": bool(env.get("AMAP_WEB_SERVICE_KEY") or env.get("AMAP_API_KEY")),
        "has_openweather_api_key": bool(env.get("OPENWEATHER_API_KEY")),
        "has_tavily_api_key": bool(env.get("TAVILY_API_KEY")),
    }
