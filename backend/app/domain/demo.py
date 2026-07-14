"""End-to-end trip planning demo with a deterministic fake LLM."""

from app.domain.planner import TripPlanner
from app.domain.schemas import TripPlanningRequest


class FakeTripLLM:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, temperature=0.2):
        self.calls += 1
        if self.calls == 1:
            return (
                '{"thought":"先查天气,如果失败也继续。",'
                '"action":{"type":"tool_call","tool_name":"get_weather_forecast",'
                '"arguments":{"city":"北京,CN","days":3}}}'
            )
        if self.calls == 2:
            return (
                '{"thought":"估算三天预算。",'
                '"action":{"type":"tool_call","tool_name":"estimate_trip_budget",'
                '"arguments":{"days":3,"attractions_cost_per_day":180,'
                '"meals_cost_per_day":160,"hotel_cost_per_night":420,'
                '"transportation_total":260,"misc_total":200}}}'
            )
        if self.calls == 3:
            return (
                '{"thought":"检查是否超出预算。",'
                '"action":{"type":"tool_call","tool_name":"check_budget_limit",'
                '"arguments":{"budget_result":{"total":2320,"breakdown":{"attractions":540,"meals":480,"hotels":840,"transportation":260,"misc":200}},'
                '"max_budget":2500}}}'
            )
        if self.calls == 4:
            return (
                '{"thought":"检查时间和路线风险。",'
                '"action":{"type":"tool_call","tool_name":"check_itinerary_constraints",'
                '"arguments":{"itinerary_days":[{"day":1,"attractions":[{"name":"故宫","visit_minutes":180,"transfer_minutes":30},{"name":"景山公园","visit_minutes":90,"transfer_minutes":20}]},{"day":2,"attractions":[{"name":"颐和园","visit_minutes":180,"transfer_minutes":50},{"name":"圆明园","visit_minutes":120,"transfer_minutes":25}]},{"day":3,"attractions":[{"name":"八达岭长城","visit_minutes":240,"transfer_minutes":90}]}],'
                '"max_daily_minutes":600,"max_budget":2500,"estimated_budget":2320}}}'
            )
        if self.calls == 5:
            return (
                '{"thought":"生成行李和穿搭建议。",'
                '"action":{"type":"tool_call","tool_name":"generate_packing_and_outfits",'
                '"arguments":{"weather_daily":[{"date":"2026-07-08","day_weather":"多云","temp_max":31,"temp_min":23},{"date":"2026-07-09","day_weather":"阵雨","temp_max":28,"temp_min":22},{"date":"2026-07-10","day_weather":"晴","temp_max":32,"temp_min":24}],'
                '"itinerary_days":[{"day":1,"attractions":[{"name":"故宫"}]},{"day":2,"attractions":[{"name":"颐和园"}]},{"day":3,"attractions":[{"name":"八达岭长城"}]}]}}}'
            )
        return (
            '{"thought":"所有工具都已执行,生成最终方案。",'
            '"action":{"type":"final_answer","content":"北京3日游方案:\\nDay 1 故宫-景山,控制在半天核心游览。\\nDay 2 颐和园-圆明园,以西北片区为主减少折返。\\nDay 3 八达岭长城,单独安排并预留交通时间。\\n预算约2320元,低于2500元上限。路线风险: Day 3换乘较长,建议早出发。天气工具当前可失败不阻塞,正式运行时以OpenWeather返回为准。行李: 证件、充电器、轻便雨衣、防晒、防滑运动鞋。洋葱穿衣: Day1短袖+轻薄外套, Day2短袖+雨衣, Day3短袖+防晒+运动鞋。"}}'
        )


def run_demo() -> None:
    planner = TripPlanner(llm=FakeTripLLM())
    response = planner.plan(TripPlanningRequest(
        city="北京",
        start_date="2026-07-08",
        days=3,
        travelers=2,
        max_budget=2500,
        preferences=["历史文化", "亲子", "长城"],
        special_requirements="希望不要太赶",
    ))
    print(response.content)
    print(f"steps={response.step_count}")
    for step in response.raw_steps:
        print(step["iteration"], step["action_type"], step["tool_name"])


if __name__ == "__main__":
    run_demo()
