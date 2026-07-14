"""Small command-line demo for the handwritten Agent loop."""

from .agent import HandwrittenAgent


def run_demo() -> None:
    agent = HandwrittenAgent(max_iterations=2)
    result = agent.run(
        "请用不超过120字说明你会如何规划一个北京2日亲子游。"
        "现在没有可用工具,请直接给最终回答。"
    )
    print(result.content)
    print(f"steps={len(result.steps)}")


if __name__ == "__main__":
    run_demo()
