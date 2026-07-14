"""Business integration layer for TripWeave Agent."""

from typing import Callable, Optional

from app.core.agent import HandwrittenAgent
from app.core.llm import OpenAICompatibleLLM
from app.core.memory import MemoryManager
from app.core.prompt import PromptBuilder
from app.core.types import AgentStep
from app.domain.schemas import TripPlanningRequest, TripPlanningResponse
from app.tools import create_default_tool_registry


TRIP_PLANNER_SYSTEM_PROMPT = """你是一个旅游规划Agent。
你必须使用工具来完成关键信息检查,再输出最终行程。

工作规则:
1. 用户信息已经完整,不得向用户追问缺失信息。
2. 第一步必须调用 search_poi 搜索真实景点或餐饮/住宿候选,不要只凭常识编造地点。
3. 优先调用 get_weather_forecast 查询天气。如果天气工具失败,最终结果里说明天气暂不可用,但继续规划。
4. 需要估计景点之间移动时,优先调用 estimate_route。没有路线数据时才允许保守估算。
5. 必须调用 estimate_trip_budget 估算预算。
6. 如果用户给了 max_budget,必须调用 check_budget_limit。
7. 必须调用 check_itinerary_constraints 检查每日时间、路线和预算风险。
8. 如果用户需要出行准备,必须调用 generate_packing_and_outfits。
9. 最终回答必须包含: 每日行程、真实地点依据、预算摘要、冲突/调整说明、行李清单、洋葱穿衣法日历。
10. 所有中间步骤必须用JSON tool_call,最后用 final_answer。
"""


class TripPlanner:
    """Facade used by API/CLI to run the handwritten Agent for trip planning."""

    def __init__(self, llm: Optional[OpenAICompatibleLLM] = None):
        self.llm = llm

    def plan(
        self,
        request: TripPlanningRequest,
        on_step: Optional[Callable[[dict], None]] = None,
    ) -> TripPlanningResponse:
        memory = MemoryManager(window_size=12)
        memory.update_state("city", request.city)
        memory.update_state("start_date", request.start_date)
        memory.update_state("days", request.days)
        memory.update_state("travelers", request.travelers)
        memory.update_state("max_budget", request.max_budget)
        memory.update_state("preferences", request.preferences)

        agent = HandwrittenAgent(
            llm=self.llm,
            memory=memory,
            prompt_builder=PromptBuilder(TRIP_PLANNER_SYSTEM_PROMPT),
            tool_registry=create_default_tool_registry(),
            max_iterations=16,
            required_tools=_required_tools(request),
            on_step=(lambda step: on_step(_step_to_dict(step))) if on_step else None,
        )

        result = agent.run(_build_task(request))
        return TripPlanningResponse(
            content=result.content,
            step_count=len(result.steps),
            raw_steps=[_step_to_dict(step) for step in result.steps],
            warning=None if result.content else "Agent returned empty content",
        )


def _required_tools(request: TripPlanningRequest) -> list:
    tools = [
        "search_poi",
        "get_weather_forecast",
        "estimate_trip_budget",
        "check_itinerary_constraints",
    ]
    if request.max_budget > 0:
        tools.append("check_budget_limit")
    if request.include_packing:
        tools.append("generate_packing_and_outfits")
    return tools


def _step_to_dict(step: AgentStep) -> dict:
    return {
        "iteration": step.iteration,
        "thought": step.action.thought,
        "action_type": step.action.type,
        "tool_name": step.action.tool_name,
        "arguments": step.action.arguments,
        "observation": step.observation,
        "raw_output": step.raw_output,
    }


def _build_task(request: TripPlanningRequest) -> str:
    preferences = ", ".join(request.preferences) if request.preferences else "无特别偏好"
    budget_text = f"{request.max_budget}元" if request.max_budget > 0 else "未设置"
    packing_text = "需要" if request.include_packing else "不需要"

    return f"""
请规划一个完整旅行方案。

用户需求:
- 目的地: {request.city}
- 出发日期: {request.start_date}
- 天数: {request.days}
- 出行人数: {request.travelers}
- 预算上限: {budget_text}
- 偏好: {preferences}
- 节奏: {request.pace}
- 住宿偏好: {request.accommodation}
- 交通偏好: {request.transportation}
- 特殊要求: {request.special_requirements or "无"}
- 是否需要行李和穿搭建议: {packing_text}

不要询问用户补充信息。你已经有足够信息开始规划。
你的第一步必须是 search_poi 工具调用:
{{
  "thought": "先搜索真实POI作为行程依据。",
  "action": {{
    "type": "tool_call",
    "tool_name": "search_poi",
    "arguments": {{"city": "{request.city}", "keyword": "{preferences}", "limit": 8}}
  }}
}}

工具使用要求:
- 先用 search_poi(city, keyword) 获取真实候选地点。keyword 可来自偏好,例如 历史文化、博物馆、公园、酒店。
- 规划跨区域景点时,用 estimate_route(origin, destination, city, mode) 估算路程。
- 用工具完成天气、预算、约束检查和行李穿搭分析。
- 你可以先拟定候选 itinerary_days, 再传给约束和穿搭工具。

itinerary_days 的每一天建议格式:
[
  {{
    "day": 1,
    "attractions": [
      {{"name": "景点名", "visit_minutes": 120, "transfer_minutes": 30}}
    ]
  }}
]

最终回答请用中文,结构清晰,但不要输出JSON。
"""
