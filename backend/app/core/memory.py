"""Memory manager for the handwritten Agent."""

from collections import deque
from typing import Any, Deque, Dict, List, cast

from .types import ChatMessage


class MemoryManager:
    """Stores short-term dialogue and long-lived task state."""

    def __init__(self, window_size: int = 8):
        self.window_size = window_size
        self.messages: Deque[ChatMessage] = deque(maxlen=window_size)
        self.tool_traces: Deque[Dict[str, Any]] = deque(maxlen=window_size)
        self.state: Dict[str, Any] = {}

    def add_message(self, role: str, content: str) -> None:
        self.messages.append(ChatMessage(role=cast(Any, role), content=content))

    def add_tool_trace(self, tool_name: str, arguments: Dict[str, Any], observation: Any) -> None:
        self.tool_traces.append({
            "tool_name": tool_name,
            "arguments": arguments,
            "observation": observation,
        })

    def update_state(self, key: str, value: Any) -> None:
        self.state[key] = value

    def get_messages(self) -> List[ChatMessage]:
        return list(self.messages)

    def get_context(self) -> Dict[str, Any]:
        return {
            "messages": [message.__dict__ for message in self.messages],
            "tool_traces": list(self.tool_traces),
            "state": self.state,
        }
