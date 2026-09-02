"""human_gate：高危操作的审批闸口——interrupt 冻结等答复，回注后执行或拒绝"""

from langgraph.types import interrupt

from app.models.schemas import AgentState, Observation
from app.tools.base import run_tool


def human_gate_node(state: AgentState) -> dict:
    task = state["pending_approval"]

    answer = interrupt({
        "task_id":task.id,
        "question": f"任务{task.id}请求执行高风险工具execute_python",
        "code": ((task.tool_args or {}).get("code", "")),
    })

    approved = bool(answer.get("approved"))

    if approved:
        obs = run_tool(task.tool, {**(task.tool_args or {}), "task_id": task.id})
    else:
        obs = Observation(
            task_id=task.id, tool=task.tool or "", success=False,
            summary="", error="用户拒绝了本次高危操作",
        )
    print("✅ 审批通过，已执行" if approved else "🚫 审批拒绝，任务标记失败",
          f"：{obs.error or obs.summary[:60]}")

    # W4-3 教训：checkpoint 每步之间有序列化边界，pending_approval 和 plan
    # 里的同名任务已是两份独立拷贝——改状态必须找到 plan 列表里的那一份来改
    for t in state["plan"]:
        if t.id == task.id:
            t.status = "completed" if obs.success else "failed"
            break

    return {
        "observations": [obs],
        "pending_approval": None,
        "current_task": state["current_task"] + 1,
        "plan": state["plan"],
    }

