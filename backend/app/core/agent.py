"""Handwritten ReAct-style Agent loop."""

import json
import re
from typing import Any, Callable, Dict, List, Optional, Protocol

from .llm import OpenAICompatibleLLM
from .memory import MemoryManager
from .prompt import PromptBuilder
from .types import AgentAction, AgentResult, AgentStep, ChatMessage


class ToolRegistryLike(Protocol):
    def schemas(self) -> List[Dict[str, Any]]:
        ...

    def call(self, name: str, arguments: Dict[str, Any]) -> Any:
        ...


class AgentOutputParser:
    """Parses the strict JSON action emitted by the model."""

    @staticmethod
    def parse(raw_output: str) -> AgentAction:
        data = AgentOutputParser._loads_json(raw_output)
        action_data = data.get("action") or {}
        action_type = action_data.get("type")
        if action_type not in {"tool_call", "final_answer"}:
            raise ValueError(f"Unsupported action type: {action_type}")

        return AgentAction(
            type=action_type,
            thought=str(data.get("thought") or ""),
            tool_name=action_data.get("tool_name"),
            arguments=action_data.get("arguments") or {},
            content=str(action_data.get("content") or ""),
        )

    @staticmethod
    def _loads_json(raw_output: str) -> Dict[str, Any]:
        text = raw_output.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text).strip()
            text = re.sub(r"```$", "", text).strip()
        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start:end + 1]
        return json.loads(text)


class HandwrittenAgent:
    """A minimal Agent loop independent from Agent frameworks."""

    def __init__(
        self,
        llm: Optional[OpenAICompatibleLLM] = None,
        memory: Optional[MemoryManager] = None,
        prompt_builder: Optional[PromptBuilder] = None,
        tool_registry: Optional[ToolRegistryLike] = None,
        max_iterations: int = 6,
        required_tools: Optional[List[str]] = None,
        on_step: Optional[Callable[[AgentStep], None]] = None,
    ):
        self.llm = llm or OpenAICompatibleLLM.from_env()
        self.memory = memory or MemoryManager()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.tool_registry = tool_registry
        self.max_iterations = max_iterations
        self.required_tools = required_tools or []
        self.on_step = on_step

    def run(self, task: str) -> AgentResult:
        self.memory.add_message("user", task)
        steps: List[AgentStep] = []
        scratchpad: List[Dict[str, Any]] = []
        called_tools = set()

        for iteration in range(1, self.max_iterations + 1):
            tool_schemas = self.tool_registry.schemas() if self.tool_registry else []
            prompt = self.prompt_builder.build(
                task=task,
                memory_context=self.memory.get_context(),
                tool_schemas=tool_schemas,
                scratchpad=scratchpad,
            )

            raw_output = self.llm.chat([
                ChatMessage(role="system", content="你是严格遵循JSON输出协议的Agent执行器。"),
                ChatMessage(role="user", content=prompt),
            ])
            action = self._parse_or_repair(raw_output)

            if action.type == "final_answer":
                missing_tools = [
                    tool_name
                    for tool_name in self.required_tools
                    if tool_name not in called_tools
                ]
                if missing_tools:
                    observation = {
                        "error": "final_answer rejected because required tools have not been called.",
                        "missing_required_tools": missing_tools,
                    }
                    scratchpad.append({
                        "iteration": iteration,
                        "thought": action.thought,
                        "tool_name": None,
                        "arguments": {},
                        "observation": observation,
                    })
                    steps.append(AgentStep(
                        iteration=iteration,
                        prompt=prompt,
                        raw_output=raw_output,
                        action=action,
                        observation=observation,
                    ))
                    self._notify_step(steps[-1])
                    continue

                self.memory.add_message("assistant", action.content)
                steps.append(AgentStep(
                    iteration=iteration,
                    prompt=prompt,
                    raw_output=raw_output,
                    action=action,
                ))
                self._notify_step(steps[-1])
                return AgentResult(content=action.content, steps=steps, state=self.memory.state)

            observation = self._execute_tool(action)
            if action.tool_name:
                called_tools.add(action.tool_name)
            self.memory.add_tool_trace(action.tool_name or "", action.arguments, observation)
            scratchpad.append({
                "iteration": iteration,
                "thought": action.thought,
                "tool_name": action.tool_name,
                "arguments": action.arguments,
                "observation": self._compact_observation(observation),
            })
            steps.append(AgentStep(
                iteration=iteration,
                prompt=prompt,
                raw_output=raw_output,
                action=action,
                observation=observation,
            ))
            self._notify_step(steps[-1])

        result = AgentResult(
            content="Agent reached max_iterations without final_answer.",
            steps=steps,
            state=self.memory.state,
        )
        return result

    def _notify_step(self, step: AgentStep) -> None:
        if self.on_step:
            self.on_step(step)

    def _execute_tool(self, action: AgentAction) -> Any:
        if not self.tool_registry:
            return {
                "error": "No tool registry is available.",
                "requested_tool": action.tool_name,
                "arguments": action.arguments,
            }
        if not action.tool_name:
            return {"error": "tool_name is required for tool_call"}
        try:
            return self.tool_registry.call(action.tool_name, action.arguments)
        except Exception as error:
            return {
                "error": str(error),
                "tool_name": action.tool_name,
                "arguments": action.arguments,
            }

    def _compact_observation(self, observation: Any) -> Any:
        if not isinstance(observation, dict):
            return observation

        if isinstance(observation.get("pois"), list):
            pois = observation.get("pois") or []
            return {
                "ok": observation.get("ok"),
                "provider": observation.get("provider"),
                "city": observation.get("city"),
                "keyword": observation.get("keyword"),
                "poi_count": len(pois),
                "pois": [
                    {
                        "name": poi.get("name"),
                        "address": poi.get("address"),
                        "rating": poi.get("rating"),
                        "location": poi.get("location"),
                    }
                    for poi in pois[:5]
                    if isinstance(poi, dict)
                ],
            }

        if isinstance(observation.get("daily"), list):
            return {
                "ok": observation.get("ok"),
                "provider": observation.get("provider"),
                "city": observation.get("city"),
                "country": observation.get("country"),
                "daily": observation.get("daily", [])[:5],
            }

        if observation.get("distance_meters") is not None:
            return {
                "ok": observation.get("ok"),
                "provider": observation.get("provider"),
                "mode": observation.get("mode"),
                "origin": observation.get("origin"),
                "destination": observation.get("destination"),
                "distance_meters": observation.get("distance_meters"),
                "duration_minutes": observation.get("duration_minutes"),
            }

        if observation.get("checklist") or observation.get("onion_layering_calendar"):
            return {
                "ok": observation.get("ok"),
                "checklist": observation.get("checklist"),
                "onion_layering_calendar": observation.get("onion_layering_calendar"),
            }

        return observation

    def _parse_or_repair(self, raw_output: str) -> AgentAction:
        try:
            return AgentOutputParser.parse(raw_output)
        except Exception:
            repair_prompt = "\n".join([
                "下面是一段不合法或不符合协议的Agent输出。",
                "请只返回一个合法JSON对象,不要解释,不要Markdown。",
                "合法格式如下:",
                '{"thought":"...","action":{"type":"tool_call或final_answer","tool_name":"...","arguments":{},"content":"..."}}',
                "原始输出:",
                raw_output,
            ])
            repaired = self.llm.chat([
                ChatMessage(role="system", content="你是JSON修复器,只输出合法JSON。"),
                ChatMessage(role="user", content=repair_prompt),
            ], temperature=0)
            return AgentOutputParser.parse(repaired)
