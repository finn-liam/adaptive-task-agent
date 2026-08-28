"""图的组装车间：把各个节点按边连起来"""
from langgraph.graph import END, START, StateGraph

from app.agent.executor import executor_node
from app.agent.final_answer import final_answer_node
from app.agent.planner import make_planner
from app.models.schemas import AgentState


def build_graph():
    g = StateGraph(AgentState)
    # AgentState：等于是一份说明书，在schema中定义了字段以及类型
    def planner_node(state: AgentState) -> dict:
        print("正在拆解目标……")
        plan = make_planner()(state["user_goal"])
        print(f"规划依据:{plan.reasoning}\n")
        return {"plan":plan.tasks,"current_task":0,"status":"executing"}

    def route_after_executor(state: AgentState) -> str:
        """指针走没走到头？没走完就回自己，干完了放行"""
        if state["current_task"] >= len(state["plan"]):
            return "done"
        return "continue"
    
    g.add_node("planner",planner_node)
    g.add_node("executor",executor_node)
    g.add_node("final_answer",final_answer_node)
    g.add_edge(START,"planner")
    g.add_edge("planner","executor")
    g.add_conditional_edges(
        "executor",
        route_after_executor,
        {"continue": "executor","done":"final_answer"}
    )
    g.add_edge("final_answer",END)

    return g.compile()      #产出可执行图