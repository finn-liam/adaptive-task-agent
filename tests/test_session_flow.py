"""会话级集成测试：脚本化应答 + 桩图（真 AgentState 白板），验证 _run_goal/_turn/_edit_resend 的接线。

不开终端：InteractiveSession 用 __new__ 绕过 PromptSession 构造，_prompt 换成
按剧本吐答案的桩，_collect_input 换成挂起直到被取消的桩。被测的是 asyncio
装配本身——to_thread 消费、排队投递循环、审批分支的任务取消与重启、软停旗升降、
软停→编辑→续跑的完整回路。桩图的 n1 里竖软停旗（trap），让"第一次 Ctrl-C"
的效果确定性地落在 n1 之后的节点边界上。
"""

import asyncio
from threading import Event

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agent.graph import make_initial_state
from app.agent.runner import COMPLETED
from app.models.schemas import AgentState, Observation, Task
from app.ui import session as session_mod
from app.ui.session import InteractiveSession


def _session(scripted_answers):
    s = InteractiveSession.__new__(InteractiveSession)
    s.fixed = False
    s.stop_event = Event()
    s.queued = []
    s._last_ctrl_c = 0.0
    s.run_id = ""
    s._answers = list(scripted_answers)
    s._seen = []

    async def fake_prompt(message, default=None):
        s._seen.append((message, default))
        return s._answers.pop(0)

    s._prompt = fake_prompt

    async def fake_collect():          # 占住"常驻输入位"，挂起直到被 cancel
        await asyncio.Event().wait()

    s._collect_input = fake_collect
    return s


def _obs(tag):
    return Observation(task_id=tag, tool="search_web", success=True, summary=tag)


def _stub_graph(trap=None, with_gate=False):
    """桩图挂真 AgentState 白板：不联网不调 LLM，checkpoint/interrupt/路由机制全真"""
    g = StateGraph(AgentState)

    def n1(state):
        if trap:
            trap()                     # 模拟"n1 执行途中用户按下第一次 Ctrl-C"
        update = {"status": "executing",
                  "plan": [Task(id="t1", description="桩任务", tool="search_web")]}
        if with_gate:
            update["pending_approval"] = Task(
                id="t9", description="高危算术", tool="execute_python",
                tool_args={"code": "1+1"})
        return update

    def gate(state):
        answer = interrupt({"task_id": "t9"})
        return {"observations": [_obs(f"gate:{answer.get('approved')}")],
                "pending_approval": None}

    def after(state):
        return {"status": "done", "final_answer": "ok",
                "observations": [_obs(f"update:{state.get('user_update')}")]}

    g.add_node("n1", n1)
    if with_gate:
        g.add_node("gate", gate)
    g.add_node("after", after)
    g.add_edge(START, "n1")
    g.add_edge("n1", "gate" if with_gate else "after")
    if with_gate:
        g.add_edge("gate", "after")
    g.add_edge("after", END)
    return g.compile(checkpointer=InMemorySaver())


def _state_of(graph, run_id):
    return graph.get_state({"configurable": {"thread_id": run_id}}).values


def _summaries(v):
    return [o.summary for o in v["observations"]]


def test_run_goal_soft_stop_then_edit_resume(monkeypatch):
    """软停 →（编辑重发直接回车=原样续跑）→ 跑完：完整回路，节点不重跑"""
    s = _session([""])
    graph = _stub_graph(trap=s.stop_event.set)   # n1 执行途中软停旗被竖起
    monkeypatch.setattr(session_mod, "build_graph", lambda: graph)

    asyncio.run(s._run_goal("测试目标"))

    assert s.run_id
    v = _state_of(graph, s.run_id)
    assert v["status"] == "done"
    # 只有一条 after 回执（update:None）：n1 之后暂停，原样续跑没注入指示，
    # 也没把 n1 重跑一遍（重跑会多出一条 update 或改变顺序）
    assert _summaries(v) == ["update:None"]
    # 软停已送达并降旗（下一轮不会被残留旗再次暂停）
    assert not s.stop_event.is_set()
    # 编辑重发的提示符确实出现过
    assert any(msg.startswith(("已暂停", "编辑后回车发送"))
               for msg, _ in s._seen)


def test_turn_delivers_queued_message_then_completes():
    s = _session([])
    s.queued = ["改搜中文教程"]                # 模拟 run 期间用户排队的消息
    graph = _stub_graph()
    cfg = {"configurable": {"thread_id": "t1"}}
    status = asyncio.run(s._turn(graph, make_initial_state("t1", "目标"), cfg))
    assert status == COMPLETED
    assert s.queued == []                      # 投递即清空，不会二次触发
    # 注入的 user_update 真的进了白板，after 节点看到了
    assert "update:改搜中文教程" in _summaries(_state_of(graph, "t1"))


def test_turn_handles_approval_branch():
    graph = _stub_graph(with_gate=True)
    s = _session(["y"])                        # 审批提示符答 y
    cfg = {"configurable": {"thread_id": "t2"}}
    status = asyncio.run(s._turn(graph, make_initial_state("t2", "目标"), cfg))
    assert status == COMPLETED
    # 审批分支真的问了人，且回答被回注 interrupt()
    assert s._seen[0][0].startswith("允许执行")
    assert "gate:True" in _summaries(_state_of(graph, "t2"))


def test_edit_resend_prefills_all_queued_messages():
    s = _session(["修改后的指示"])
    s.queued = ["原始想法", "补充"]
    msg = asyncio.run(s._edit_resend())
    assert msg == "修改后的指示"
    assert s.queued == []
    # 预填 = 全部排队消息按行合并（prompt(default=...) 原生可编辑）
    message, default = s._seen[0]
    assert message.startswith("编辑后回车发送")
    assert default == "原始想法\n补充"


def test_edit_resend_empty_queue_empty_input_means_continue():
    s = _session([""])
    assert asyncio.run(s._edit_resend()) is None
