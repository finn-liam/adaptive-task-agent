"""重规划安全网回归测试。

事故背景（run 71ae296f，2026-10-09）：第 3 次重规划时 LLM 为凑"任务≤8"删掉了
已完成的 t1~t4，新增的 t9/t10 还 depends_on 被删的 t3/t4——executor 的
next(t for t in plan if t.id == d) 找不到 id 抛 StopIteration，穿透进 langgraph
的生成器调度器后被 PEP 479 转成 RuntimeError，整条 run 崩溃。

两道防线：
- replanner 收尾合同校验（治根）：补回被违约删除的已完成任务 + 剔除悬空 depends_on；
- executor 名册检查（治崩）：悬空依赖按"未就绪"跳过并记失败回执，绝不再抛异常。
"""

import app.agent.replanner as replanner
from app.agent.executor import executor_node
from app.models.schemas import EvaluationResult, Plan, Task


class _FakeStructuredLLM:
    """替身：不开网络，直接吐一份'违约'的新计划（复刻真实事故的 LLM 输出形态）"""

    def with_structured_output(self, schema, method=None):
        return self

    def invoke(self, prompt):
        return Plan(reasoning="模拟违约输出：删掉已完成任务凑数", tasks=[
            Task(id="t5", description="保留的旧任务", tool="search_web", status="completed"),
            Task(id="t9", description="新增任务，依赖被删的 t3", tool="search_github",
                 tool_args={"action": "search", "query": "x"}, depends_on=["t3"]),
        ])


def _old_plan():
    return [
        Task(id="t1", description="已完成1", tool="fetch_url", status="completed"),
        Task(id="t2", description="已完成2", tool="fetch_url", status="completed"),
        Task(id="t3", description="已完成3", tool="search_github", status="completed"),
        Task(id="t4", description="失败任务（允许被替换）", tool="fetch_url", status="failed"),
        Task(id="t5", description="保留的旧任务", tool="search_web", status="completed"),
    ]


def test_replanner_resurrects_completed_and_fixes_deps(monkeypatch):
    monkeypatch.setattr(replanner, "make_llm", lambda: _FakeStructuredLLM())
    state = {
        "plan": _old_plan(),
        "evaluation": EvaluationResult(success=False, reason="缺正文",
                                       need_replan=True, missing_info="正文内容"),
        "user_goal": "分析某 GitHub 用户仓库",
        "replan_count": 2,
        "observations": [],
    }
    out = replanner.replanner_node(state)
    ids = {t.id for t in out["plan"]}
    # ① 已完成的 t1~t3 被模型违约删除后必须补回（失败的 t4 允许被替换，不要求保留）
    assert {"t1", "t2", "t3"} <= ids
    # ② t3 补回后，t9 的依赖不再悬空，且全计划无任何悬空引用
    assert all(d in ids for t in out["plan"] for d in t.depends_on)
    # ③ 指针指向第一个待执行任务（t9），不会误指向补回的已完成任务
    first_pending = next(i for i, t in enumerate(out["plan"]) if t.status == "pending")
    assert out["current_task"] == first_pending


def test_executor_treats_dangling_dep_as_not_ready():
    # 兜底防线：即使悬空依赖漏进白板（比如首次规划就幻觉了 id），也只是跳过并记失败回执
    t9 = Task(id="t9", description="依赖不存在的任务", tool="search_web", depends_on=["t3"])
    out = executor_node({"plan": [t9], "current_task": 0})
    obs = out["observations"][0]
    assert obs.success is False
    assert "t3" in obs.error
    assert out["current_task"] == 1          # 指针照样前进，图不会卡死
    assert t9.status == "failed"
