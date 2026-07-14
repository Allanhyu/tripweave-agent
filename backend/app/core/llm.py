"""OpenAI-compatible LLM client without Agent framework dependencies."""

import json
import os
import socket
from pathlib import Path
from typing import List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .types import ChatMessage
from app.runtime_settings import load_backend_env


class LLMError(RuntimeError):
    """Raised when the LLM provider returns an unusable response."""


class OpenAICompatibleLLM:
    """Minimal chat-completions client for OpenAI-compatible providers."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: int = 120,
        response_format: str = "",
    ):
        if not api_key:
            raise LLMError("LLM_API_KEY or OPENAI_API_KEY is not configured")

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.response_format = response_format

    @classmethod
    def from_env(cls) -> "OpenAICompatibleLLM":
        env = _read_backend_env()
        api_key = _env_value(env, "LLM_API_KEY") or _env_value(env, "OPENAI_API_KEY")
        base_url = _env_value(env, "LLM_BASE_URL") or _env_value(env, "OPENAI_BASE_URL") or "https://api.openai.com/v1"
        model = _env_value(env, "LLM_MODEL_ID") or _env_value(env, "OPENAI_MODEL") or "gpt-4o-mini"
        timeout = int(_env_value(env, "LLM_TIMEOUT") or "120")
        response_format = _env_value(env, "LLM_RESPONSE_FORMAT")
        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
            response_format=response_format,
        )

    def chat(self, messages: List[ChatMessage], temperature: float = 0.2) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": message.role, "content": message.content} for message in messages],
            "temperature": temperature,
        }
        if self.response_format == "json_object":
            payload["response_format"] = {"type": "json_object"}
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise LLMError(f"LLM request failed: HTTP {error.code} {detail}") from error
        except (TimeoutError, socket.timeout) as error:
            raise LLMError(f"LLM request timed out after {self.timeout}s. Increase LLM_TIMEOUT or retry later.") from error
        except URLError as error:
            raise LLMError(f"LLM connection failed: {error.reason}") from error

        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"LLM response has no choices: {data}")

        message = choices[0].get("message", {})
        content: Optional[str] = message.get("content") or message.get("reasoning_content")
        if not content:
            raise LLMError(f"LLM response has empty content: {data}")
        return content


def _read_backend_env() -> dict:
    return load_backend_env()


def _env_value(file_env: dict, key: str) -> str:
    return os.getenv(key) or file_env.get(key, "")
