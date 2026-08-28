"""final_answer：把所有回执汇总成给用户的最终答复"""

from app.agent.llm import make_llm
from app.models.schemas import AgentState

ANSWER_PROMPT = """
你是研究助理，用户有一个目标，系统已经执行了若干任务并收集了观察材料。

用户目标：{goal}

观察资料：
{observations}

请输出最终的答案，要求：
1. 直接围绕目标给出结论/方案。分点组织；
2. 只依据观察资料，不要编造资料中没有的信息；
3. 若某任务失败或者资料不足，明确明缺了说明；
4. 末尾附"参考来源": 从资料里挑出真正用到的URL，逐行列出。
"""

def final_answer_node(state: AgentState) -> dict:
    blocks =[]
    for o in state["observations"]:
        content = o.summary if o.success else f'失败 {o.error}'
        blocks.append(f"任务{o.task_id} (工具 {o.tool}) : \n{content}")
    prompt = (ANSWER_PROMPT
              .replace("{goal}",state["user_goal"])
              .replace("{observations}","\n\n".join(blocks))
    )

    print("\n 正在汇总最终答案……：")
    answer = make_llm().invoke(prompt).content
    print("汇总完成")
    return {"final_answer":answer,"status": "done"}