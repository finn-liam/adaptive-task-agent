"""图的组装车间：把各个节点按边连起来，并挂上断点恢复的"行车记录仪"

W4-2 新增：checkpointer（决策 D3）
- 编译图时挂上 SqliteSaver：每个节点（super-step）跑完，完整白板被快照存进 checkpoints.sqlite；
- 快照按 thread_id（= run_id）归档，进程死后凭同号恢复，从断掉的节点继续；
- 恢复粒度是节点级："至少一次"语义——死在节点中间的，恢复后该节点从头重跑。
"""

import os
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from app.agent.evaluator import evaluator_node
from app.agent.executor import executor_node
from app.agent.final_answer import final_answer_node
from app.agent.human_gate import human_gate_node
from app.agent.planner import make_planner
from app.agent.replanner import replanner_node
from app.models.schemas import AgentState


def _default_checkpointer():
    """W6：默认 SQLite；设置 USE_POSTGRES=1 + POSTGRES_URI 时切换 PostgresSaver（决策 D3 兑现）"""
    if os.environ.get("USE_POSTGRES"):
        import psycopg
        from langgraph.checkpoint.postgres import PostgresSaver
        conn = psycopg.connect(os.environ["POSTGRES_URI"], autocommit=True)
        saver = PostgresSaver(conn)
        saver.setup()          # 自动建 checkpoint 表（幂等，可重复执行）
        return saver
    conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
    return SqliteSaver(conn)


def build_graph(checkpointer=None):
    # checkpointer 参数留了注入口：测试/服务化时可以注入别的存储器（W6 换 PostgresSaver 就是这里换）
    g = StateGraph(AgentState)  # AgentState：白板的说明书，声明整张图共享哪些格子

    def planner_node(state: AgentState) -> dict:
        print("正在拆解目标……")
        plan = make_planner()(state["user_goal"])
        print(f"规划依据:{plan.reasoning}\n")
        return {"plan": plan.tasks, "current_task": 0, "status": "executing"}

    def route_after_eval(state: AgentState) -> str:
        # 注意分支顺序（W3 教训）：缺口检查优先于"跑完了"——先填缺口，再谈收工
        if (state["adaptive"]
                and state["evaluation"].need_replan
                and state["replan_count"] < 3):
            return "replan"      # 三条件=自适应模式 + 质检说缺信息 + 熔断未触发
        if state["current_task"] >= len(state["plan"]):
            return "final"       # 指针到头，全部完成
        return "next"            # 通过→下一个；失败不重规划→跳过继续

    def route_after_execute(state: AgentState) -> str:
        return "gate" if state.get("pending_approval") is not None else "evaluator"

    g.add_node("planner", planner_node)
    g.add_node("executor", executor_node)
    g.add_node("evaluator", evaluator_node)
    g.add_node("replanner", replanner_node)
    g.add_node("final_answer", final_answer_node)
    g.add_node("human_gate",human_gate_node)

    # 边的登记表：代码书写顺序与执行顺序无关（登记规则，不是播放列表）
    g.add_edge(START, "planner")
    g.add_edge("planner", "executor")
    g.add_conditional_edges(
        "executor",
        route_after_execute,
        {"gate":"human_gate","evaluator": "evaluator"}
    )
    g.add_edge("human_gate","evaluator")
    g.add_edge("replanner", "executor")          # 改完计划必然回去继续干活
    g.add_conditional_edges(                     # evaluator 出口三岔：路由现场选
        "evaluator",
        route_after_eval,
        {"next": "executor", "replan": "replanner", "final": "final_answer"},
    )
    g.add_edge("final_answer", END)

    # —— W4-2 断点恢复 / W6 Postgres 切换 ——
    # 默认 SQLite 文件库；容器部署时由环境变量切换 PostgresSaver（决策 D3）
    if checkpointer is None:
        checkpointer = _default_checkpointer()
    return g.compile(checkpointer=checkpointer)  # 挂上"行车记录仪"再出厂
