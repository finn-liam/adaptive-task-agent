"""run_stream 的节点边界测试：软停 / Command(update) 续跑 / interrupt 冻结 / 队列投递点。

用一个不联网的两节点小图 + InMemorySaver 验证交互模式的四条执行底座行为，
重点证实 langgraph 1.2 的关键语义：Command(update=...) 作为 stream 输入
= 写入白板 + 从断点继续跑（"编辑重发"和"不打断转向"全靠这条通道）。
"""

import operator
from threading import Event
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.agent.runner import (
    AWAITING_APPROVAL,
    COMPLETED,
    PAUSED_INPUT,
    PAUSED_SOFT,
    run_stream,
)


class _S(TypedDict):
    log: Annotated[list[str], operator.add]
    user_update: str | None


def _config(tid):
    return {"configurable": {"thread_id": tid}}


def _two_node_graph(trap=None):
    """n1 → n2；trap 是 n1 执行时触发的回调（测试用来在节点内部 set stop_event）"""
    g = StateGraph(_S)

    def n1(state):
        if trap:
            trap()
        return {"log": ["n1"]}

    def n2(state):
        # n2 把白板上的 user_update 原样记进日志——验证 Command(update) 真的进了状态
        return {"log": [f"n2:{state.get('user_update')}"]}

    g.add_node("n1", n1)
    g.add_node("n2", n2)
    g.add_edge(START, "n1")
    g.add_edge("n1", "n2")
    g.add_edge("n2", END)
    return g.compile(checkpointer=InMemorySaver())


def _gate_graph():
    g = StateGraph(_S)

    def gate(state):
        answer = interrupt({"q": "允许吗？"})
        return {"log": [f"gate:{answer}"]}

    g.add_node("gate", gate)
    g.add_edge(START, "gate")
    g.add_edge("gate", END)
    return g.compile(checkpointer=InMemorySaver())


def test_soft_stop_pauses_at_node_boundary():
    ev = Event()
    graph = _two_node_graph(trap=ev.set)     # n1 跑的途中软停旗被竖起
    status, payload = run_stream(
        graph, {"log": [], "user_update": None}, _config("soft"),
        stop_event=ev,
    )
    assert status == PAUSED_SOFT
    assert payload is None
    # 只跑完 n1 就停住：checkpoint 落在 n1 之后、n2 之前
    assert graph.get_state(_config("soft")).values["log"] == ["n1"]


def test_resume_with_command_update_continues_and_injects():
    # 用软停法造一条"停在 n1 之后"的现场，再验证"续跑 + 注入"通道
    ev = Event()
    graph = _two_node_graph(trap=ev.set)
    cfg = _config("update")
    run_stream(graph, {"log": [], "user_update": None}, cfg, stop_event=ev)

    status, _ = run_stream(
        graph, Command(update={"user_update": "改搜中文教程"}), cfg,
    )
    assert status == COMPLETED
    # n1（软停前）→ 注入的指示被 n2 看到（Command(update) 生效且图继续跑）
    assert graph.get_state(cfg).values["log"] == ["n1", "n2:改搜中文教程"]


def test_interrupt_freezes_and_resume_answers():
    graph = _gate_graph()
    cfg = _config("gate")
    status, payload = run_stream(graph, {"log": [], "user_update": None}, cfg)
    assert status == AWAITING_APPROVAL
    assert payload[0].value == {"q": "允许吗？"}      # chunk 里带着 interrupt 载荷

    status, _ = run_stream(graph, Command(resume={"approved": True}), cfg)
    assert status == COMPLETED
    assert "gate:{'approved': True}" in graph.get_state(cfg).values["log"]


def test_pending_input_pauses_without_stopping_graph():
    graph = _two_node_graph()
    cfg = _config("input")
    status, _ = run_stream(
        graph, {"log": [], "user_update": None}, cfg,
        has_input=lambda: True,               # 队列里已有消息
    )
    assert status == PAUSED_INPUT
    assert graph.get_state(cfg).values["log"] == ["n1"]

    status, _ = run_stream(
        graph, Command(update={"user_update": "msg"}), cfg,
        has_input=lambda: False,              # 队列已清空，一路跑完
    )
    assert status == COMPLETED
