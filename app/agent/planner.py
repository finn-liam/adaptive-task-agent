"""Planner —— 把用户目标翻译成结构化任务清单"""

from app.agent.llm import make_llm
from app.models.schemas import Plan, TOOL_NAMES
from pydantic import ValidationError

PLANNER_PROMPT = """
你是一名资深技术架构师，擅长把模糊目标拆成可执行的调研步骤。

请按以下规则产出任务清单：
1. tool 字段只能逐字使用这份名单里的名字：{tools}
2. 每个任务的 description 必须是可直接执行的一句话指令：
   "抓取 X 页面正文并提取安装方式"是好例子；"了解依赖情况"是坏例子（太含糊）。
3. 任务总数 3~8 个，按执行顺序排列，前面任务的产出应能被后面任务利用。
4. 不要安排任何总结、汇报类任务，最终答复由系统的其他部分负责。

用户目标：{goal}
"""


def make_planner(max_attempts: int = 3):
    """返回一个 goal -> Plan 的规划函数"""
    llm = make_llm()
    structured_llm = llm.with_structured_output(Plan,method="function_calling")

    def planner(goal: str) -> Plan:
        base_prompt = (
            PLANNER_PROMPT
            .replace("{tools}", ", ".join(TOOL_NAMES))
            .replace("{goal}", goal)
        )
        prompt = base_prompt

        for attempt in range(1,max_attempts + 1):
            try:
                return structured_llm.invoke(prompt)
            except ValidationError as e:
                prompt = base_prompt + (
                    "\n\n你上一次的输出未通过校验，错误如下：\n"
                    f"{e}\n"
                    "请针对以上问题修正，重新输出完整、合法的任务计划。"
                )
                
        raise RuntimeError(f"连续{max_attempts}次产出非法计划，放弃治疗")
    return planner