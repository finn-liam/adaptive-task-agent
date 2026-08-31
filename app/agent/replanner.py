"""replanner：根据评估缺口增量修改计划（三条约束见 plan.md §5）"""

from app.agent.llm import make_llm
from app.models.schemas import AgentState, Plan

REPLAN_PROMPT = """你是重规划专家，一个执行中的计划遇到了信息缺口，需要你增量修改。

用户总目标：{goal}

当前计划(√=已完成 X=失败 o=待执行)
{plan_view}

质量判断：{reason}
信息缺口：{missing}

修改约束(全部必须遵守):
1. 已完成任务(√)原样保留: id、descriptions、tool、tool_args 一字不改;
2. 只允许新增任务，或修改失败/待执行任务;
3. 新增任务的 depends_on 写清依赖的已有任务 id;
4. reasoning 里只先指认缺口，再说明哪个新任务负责填补;
5. 任务总数不超过8个。
7. 系统没有任何工具能"处理上一步抓到的内容"：提取、总结、筛选类需求一律不要建任务
   （最终答复环节会自动完成）；tool_args 必须是具体参数（完整 URL、文件路径、搜索关键词），
   只规划"获取信息"类任务。
"""

def replanner_node(state: AgentState) -> dict:
    plan = state["plan"]
    lines = []
    for t in plan:
        mark = {"completed": "√","failed":"X"}.get(t.status, "o")
        lines.append(f"{mark} {t.id} ({t.tool}): {t.description}")
    ev = state["evaluation"]        #看evaluator.py中失败的返回值
    prompt = (REPLAN_PROMPT
                .replace("{goal}",state["user_goal"])
                .replace("{plan_view}", "\n".join(lines))
                .replace("{reason}", ev.reason)
                .replace("{missing}", ev.missing_info or ev.reason)
    )

    new_plan : Plan = make_llm().with_structured_output(
        Plan,method="function_calling").invoke(prompt)
# Plan(reasoning='缺口是教程内容。改用中文关键词重搜',
#      tasks=[task1, task2, task3(改写query), task4(新增)])

    old_status = {t.id: t.status for t in plan}
    for t in new_plan.tasks:
        if old_status.get(t.id) == "completed":
            t.status = "completed"
        else:
            t.status = "pending"        # 其余（失败/新增/被改的）一律重置为待执行
# 增加新任务。
    added = [t.id for t in new_plan.tasks if t.id not in old_status]

    print(f"\n🛠️  第{state["replan_count"]+1}次重规划 | 新增{added or "无"} | {new_plan.reasoning[:60]}")

    pending_idx = next(
        (i for i, t in enumerate(new_plan.tasks) if t.status == "pending"),
        None,
    )
    #  若 pending_idx 是 None（极端：LLM 全标 completed）→ 兜底：重置刚失败的
    if pending_idx is None:
        # 极端兜底：计划里居然没有待执行任务 → 强制重置刚失败的那个
        failed_id = state["observations"][-1].task_id
        pending_idx = next(i for i, t in enumerate(new_plan.tasks) if t.id == failed_id)
        new_plan.tasks[pending_idx].status = "pending"

    return {
        "plan": new_plan.tasks,
        "replan_count": state["replan_count"] + 1,
        "current_task": pending_idx,
        "status": "executing",
    }