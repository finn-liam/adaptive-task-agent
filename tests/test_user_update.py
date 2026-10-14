"""user_update 通道（排队消息投递口）的回归测试。

交互模式的三条路径都汇聚到这里：
- 不打断也能转向：节点边界投递 user_update → 路由强制进 replanner；
- 中断后编辑重发：软停后修改的消息同样经 user_update 注入；
- 消费即清空：replanner 消化指示后必须置 None，防止同一条消息反复触发重规划。
"""

from app.agent import replanner
from app.agent.graph import route_after_eval
from app.models.schemas import EvaluationResult, Plan, Task


class _CapturingLLM:
    """替身：不开网络，把发给模型的 prompt 原样留下来供断言"""

    def __init__(self):
        self.prompts = []

    def with_structured_output(self, schema, method=None):
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return Plan(reasoning="按用户指示调整", tasks=[
            Task(id="t1", description="原任务", tool="search_web", status="completed"),
            Task(id="t2", description="新增任务", tool="search_web",
                 tool_args={"query": "新关键词"}, status="pending"),
        ])


def _eval_state(**over):
    state = {
        "adaptive": True,
        "evaluation": EvaluationResult(success=True, reason="没问题",
                                       need_replan=False),
        "replan_count": 0,
        "current_task": 1,
        "plan": [Task(id="t1", description="a", tool="search_web"),
                 Task(id="t2", description="b", tool="fetch_url")],
        "user_update": None,
    }
    state.update(over)
    return state


def test_user_update_forces_replan_even_when_evaluation_passes():
    # 质检说"没问题"但用户中途有指示 → 仍必须重规划（转向优先于既有计划）
    assert route_after_eval(_eval_state(user_update="改搜中文教程")) == "replan"


def test_user_update_beats_final():
    # 指针已到头、按原逻辑该收工了，但用户补充了新要求 → 先重规划再谈收工
    state = _eval_state(user_update="再补一个 GitHub 仓库分析", current_task=2)
    assert route_after_eval(state) == "replan"


def test_user_update_respects_replan_circuit_breaker():
    # 3 次熔断对用户指示同样生效：防住"指示→重规划→又投递"的死循环
    state = _eval_state(user_update="指示", replan_count=3, current_task=2)
    assert route_after_eval(state) == "final"


def test_no_user_update_keeps_original_routing():
    # 无指示时路由行为与改造前完全一致（回归保护）
    assert route_after_eval(_eval_state()) == "next"
    assert route_after_eval(_eval_state(current_task=2)) == "final"


def test_replanner_consumes_update_and_clears_it(monkeypatch):
    fake = _CapturingLLM()
    monkeypatch.setattr(replanner, "make_llm", lambda: fake)
    state = {
        "plan": [Task(id="t1", description="原任务", tool="search_web",
                      status="completed")],
        "evaluation": EvaluationResult(success=True, reason="通过",
                                       need_replan=False),
        "user_goal": "分析某仓库",
        "replan_count": 0,
        "observations": [],
        "user_update": "重点看 star 增长趋势",
    }
    out = replanner.replanner_node(state)
    # ① 指示进入了模型可见的 prompt
    assert "重点看 star 增长趋势" in fake.prompts[-1]
    # ② 消费后清空，同一条消息不会二次触发重规划
    assert out["user_update"] is None
    assert out["replan_count"] == 1
