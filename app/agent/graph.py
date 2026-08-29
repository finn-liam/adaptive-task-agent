"""图的组装车间：把各个节点按边连起来"""
from langgraph.graph import END, START, StateGraph

from app.agent.evaluator import evaluator_node
from app.agent.executor import executor_node
from app.agent.final_answer import final_answer_node
from app.agent.planner import make_planner
from app.agent.replanner import replanner_node
from app.models.schemas import AgentState


def build_graph():
    g = StateGraph(AgentState)
    # AgentState：等于是一份说明书，在schema中定义了字段以及类型
    def planner_node(state: AgentState) -> dict:
        print("正在拆解目标……")
        plan = make_planner()(state["user_goal"])
        print(f"规划依据:{plan.reasoning}\n")
        return {"plan":plan.tasks,"current_task":0,"status":"executing"}


    # def route_after_executor(state: AgentState) -> str:
    #     """指针走没走到头？没走完就回自己，干完了放行"""
    #     if state["current_task"] >= len(state["plan"]):
    #         return "done"
    #     return "continue"

    def route_after_eval(state: AgentState) ->str:
        if (state["adaptive"]
                and state["evaluation"].need_replan
                and state["replan_count"] < 3):
            return "replan"
        if state["current_task"] >= len(state["plan"]):
            return "final"
        return "next" 
    

    g.add_node("planner",planner_node)
    g.add_node("executor",executor_node)
    g.add_node("evaluator",evaluator_node)
    g.add_node("replanner",replanner_node)
    g.add_node("final_answer",final_answer_node)

    g.add_edge(START,"planner")
    g.add_edge("planner","executor")
    g.add_edge("executor", "evaluator") 
    g.add_edge("replanner","executor")
    g.add_conditional_edges(
        "evaluator",
        route_after_eval,
        {"next": "executor","replan":"replanner","final":"final_answer"}
    )
    g.add_edge("final_answer",END)

    return g.compile()      #产出可执行图