"""Local demo for tool-calling without using a real LLM."""

from app.core.agent import HandwrittenAgent
from app.tools import create_default_tool_registry


class FakeToolCallingLLM:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, temperature=0.2):
        self.calls += 1
        if self.calls == 1:
            return (
                '{"thought":"需要先估算预算。",'
                '"action":{"type":"tool_call","tool_name":"estimate_trip_budget",'
                '"arguments":{"days":3,"attractions_cost_per_day":150,'
                '"meals_cost_per_day":180,"hotel_cost_per_night":400,'
                '"transportation_total":300,"misc_total":200}}}'
            )
        return (
            '{"thought":"预算工具已经返回结果,可以总结。",'
            '"action":{"type":"final_answer","content":"3日游预算约2290元,主要成本来自住宿、餐饮和门票。"}}'
        )


def run_demo() -> None:
    agent = HandwrittenAgent(
        llm=FakeToolCallingLLM(),
        tool_registry=create_default_tool_registry(),
        max_iterations=3,
    )
    result = agent.run("帮我估算一个3天旅行预算")
    print(result.content)
    print(f"steps={len(result.steps)}")
    print(f"first_observation={result.steps[0].observation}")


if __name__ == "__main__":
    run_demo()
