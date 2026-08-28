"""executor：把任务从白板上取下来，交给工具，把回执放回白板"""

from app.models.schemas import AgentState, Observation
from app.tools.base import run_tool


def executor_node(state: AgentState) -> dict:
    # state可以当作是一块白板，在流程中穿梭。AgentState十一份带数据类型的说明书，按照给的字段才能使用。
    plan = state["plan"]
    idx = state["current_task"]
    task = plan[idx]

    print(f"{task.id} {task.description}")

    not_ready = [
        d for d in task.depends_on
        if next(t for t in plan if t.id == d).status != "completed"
    ]
    if not_ready:
        obs = Observation(
            task_id=task.id,tool=task.tool or "",success=False,
            summary="",error=f"前置任务未完成： {not_ready}，本次跳过执行",
        )
        task.status = "failed"
        return {"observation": [obs],"current_task": idx+1,"plan":plan}
    obs = run_tool(task.tool, {**(task.tool_args or {}), "task_id": task.id})

    task.status = "completed" if obs.success else "failed"
    mark = "√" if obs.success else "X"
    print(f"{mark} {task.tool} -> {obs.error or f'拿到 {len(obs.summary)}字符'}")

    return {
        'observations': [obs],
        "current_task": idx+1,
        "plan":plan
    }
