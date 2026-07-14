"""Core data structures for the handwritten Agent loop."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


AgentActionType = Literal["tool_call", "final_answer"]


@dataclass
class ChatMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str


@dataclass
class AgentAction:
    type: AgentActionType
    thought: str = ""
    tool_name: Optional[str] = None
    arguments: Dict[str, Any] = field(default_factory=dict)
    content: str = ""


@dataclass
class AgentStep:
    iteration: int
    prompt: str
    raw_output: str
    action: AgentAction
    observation: Optional[Any] = None


@dataclass
class AgentResult:
    content: str
    steps: List[AgentStep]
    state: Dict[str, Any] = field(default_factory=dict)
