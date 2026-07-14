"""Small thread-safe TTL cache for deterministic tool calls."""

import copy
import json
import threading
import time
from typing import Any, Dict, Tuple


class TTLCache:
    """In-memory TTL cache keyed by JSON-serializable values."""

    def __init__(self):
        self._items: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, namespace: str, payload: Dict[str, Any]) -> Tuple[bool, Any]:
        key = self._key(namespace, payload)
        now = time.time()
        with self._lock:
            item = self._items.get(key)
            if not item:
                return False, None
            expires_at, value = item
            if expires_at <= now:
                self._items.pop(key, None)
                return False, None
            return True, copy.deepcopy(value)

    def set(self, namespace: str, payload: Dict[str, Any], value: Any, ttl_seconds: int) -> None:
        key = self._key(namespace, payload)
        with self._lock:
            self._items[key] = (time.time() + ttl_seconds, copy.deepcopy(value))

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    @staticmethod
    def _key(namespace: str, payload: Dict[str, Any]) -> str:
        try:
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        except TypeError:
            body = repr(payload)
        return f"{namespace}:{body}"
