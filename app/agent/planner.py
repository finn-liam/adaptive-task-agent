"""Planner —— 把用户目标翻译成结构化任务清单"""

from pydantic import ValidationError

from app.agent.llm import make_llm
from app.models.schemas import Plan
from app.tools.registry import TOOL_REGISTRY

PLANNER_PROMPT = """
你是一名资深技术架构师，擅长把模糊目标拆成可执行的调研步骤。

请按以下规则产出任务清单：
1. tool 字段只能逐字使用这份名单里的名字：{tools}
2. 每个任务的 description 必须是可直接执行的一句话指令：
   "抓取 X 页面正文并提取安装方式"是好例子；"了解依赖情况"是坏例子（太含糊）。
3. 任务总数 3~8 个，按执行顺序排列，前面任务的产出应能被后面任务利用。
4. 不要安排任何总结、汇报类任务，最终答复由系统的其他部分负责。
5. 系统没有任何工具能"处理上一步抓到的内容"：提取、总结、筛选类需求一律不要建任务
   （最终答复环节会自动完成）；tool_args 必须是具体参数（完整 URL、文件路径、搜索关键词），
   只规划"获取信息"类任务。
6. 各工具的 tool_args 必须逐字使用这些参数名：
    search_web → {"query": "关键词"}
    fetch_url → {"url": "完整网址"}
    search_github → {"action": "search", "query": "关键词"}（拉取 README 时用 {"action": "readme", "repo": "owner/仓库名"}）
    read_file → {"path": "项目内相对路径"}
    execute_python → {"code": "单个纯算术表达式"}——只许一个表达式，
    search_knowledge → {"query": "关键词"}——只检索你自己的工程笔记（本项目怎么做的），
    互联网上的通用技术知识必须用 search_web
    save_memory → {"content": "要记住的一句话"}——写入长期记忆
    禁止赋值语句、禁止 print、禁止多行；它只能算数，不能搜索或读文件。

用户目标：{goal}
"""


def make_planner(max_attempts: int = 3):
    """返回一个 goal -> Plan 的规划函数"""
    # 造实例
    llm = make_llm()
    # 逼模型按照Plan填表的新对象
    structured_llm = llm.with_structured_output(Plan,method="function_calling")

    def planner(goal: str) -> Plan:
        base_prompt = (
            PLANNER_PROMPT
            .replace("{tools}", ", ".join(TOOL_REGISTRY))
            .replace("{goal}", goal)
        )
        prompt = base_prompt

        for attempt in range(1,max_attempts + 1):
            try:
                # LLM回传JSON，交给 Plan.model_validate->schema.py质检，合格得到Plan对象（-> plan）。
                return structured_llm.invoke(prompt)
            except ValidationError as e:
                # 主要是规范工具的调用，让每次工具的调用都能在给的范围中调用。
                prompt = base_prompt + (
                    "\n\n你上一次的输出未通过校验，错误如下：\n"
                    f"{e}\n"
                    "请针对以上问题修正，重新输出完整、合法的任务计划。"
                )
                
        raise RuntimeError(f"连续{max_attempts}次产出非法计划，放弃治疗")
    return planner

# llm返回的内容
# {
#   "reasoning": "用户目标是搜索 langgraph 仓库并阅读 README。先搜索定位仓库，再抓取其主页提取信息。所以拆成两步，前序产出供后续使用。",
#   "tasks": [
#     {
#       "id": "task1",
#       "description": "用 search_github 搜索 langgraph 仓库，获取其完整 URL 和基本信息",
#       "tool": "search_github",
#       "tool_args": {"action": "search", "query": "langgraph"},
#       "depends_on": [],
#       "status": "pending"
#     },
#     {
#       "id": "task2",
#       "description": "抓取 langgraph 仓库主页，提取仓库描述和 README 正文",
#       "tool": "fetch_url",
#       "tool_args": {"url": "https://github.com/langchain-ai/langgraph"},
#       "depends_on": ["task1"],
#       "status": "pending"
#     }
#   ]
# }



# 返回的planner示例为：
# Plan(
    # reasoning='用户目标分为三步：搜索仓库、阅读 README、找教程。按顺序拆解，前序产出供后续使用。',
    # tasks=[
    #     Task(id='task1', description='用 search_github 搜索 langgraph 仓库，获取完整 URL',
    #          tool='search_github',
    #          tool_args={'action': 'search', 'query': 'langgraph'},
    #          depends_on=[],
    #          status='pending'),
    #     Task(id='task2', description='抓取 langgraph 仓库主页，提取元信息',
    #          tool='fetch_url',
    #          tool_args={'url': 'https://github.com/langchain-ai/langgraph'},
    #          depends_on=[],
    #          status='pending'),
    #     ...
    # ],
# )

