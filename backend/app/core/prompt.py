"""Prompt templates for the handwritten Agent loop."""

import json
from typing import Any, Dict, List


class PromptBuilder:
    """Builds a strict JSON ReAct prompt."""

    def __init__(self, system_instruction: str = ""):
        self.system_instruction = system_instruction or (
            "你是一个手写Agent核心的旅游规划助手。你必须按指定JSON格式输出。"
        )

    def build(
        self,
        task: str,
        memory_context: Dict[str, Any],
        tool_schemas: List[Dict[str, Any]],
        scratchpad: List[Dict[str, Any]],
    ) -> str:
        output_contract = {
            "thought": "说明你当前为什么这么做",
            "action": {
                "type": "tool_call 或 final_answer",
                "tool_name": "当type=tool_call时填写工具名",
                "arguments": "当type=tool_call时填写JSON对象",
                "content": "当type=final_answer时填写最终回答",
            },
        }

        return "\n\n".join([
            self.system_instruction,
            "任务:",
            task,
            "可用工具JSON Schema:",
            json.dumps(tool_schemas, ensure_ascii=False, indent=2),
            "记忆上下文:",
            json.dumps(memory_context, ensure_ascii=False, indent=2),
            "已执行步骤:",
            json.dumps(scratchpad, ensure_ascii=False, indent=2),
            "输出要求: 只输出一个合法JSON对象,不要使用Markdown代码块。",
            json.dumps(output_contract, ensure_ascii=False, indent=2),
        ])
