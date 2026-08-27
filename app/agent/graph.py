from langgraph.graph import END, START, StateGraph

from app.agent.planner import make_planner
from app.models.schemas import AgentState


def build_graph():
    g = StateGraph(AgentState)
    def planner_node(state: AgentState) -> dict:
        print("正在拆解目标……")
        plan = make_planner()(state["user_goal"])
        print(f"规划依据:{plan.reasoning}\n")
        return {"plan":plan.tasks,"current_task":0,"status":"executing"}

    g.add_node("planner",planner_node)
    g.add_edge(START,"planner")
    g.add_edge("planner",END)

    return g.compile()