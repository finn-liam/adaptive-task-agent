import argparse
import uuid

from app.agent.graph import build_graph


def main():
    parser = argparse.ArgumentParser(description="Adaptive Task Planning Agent")
    parser.add_argument("goal",help="要完成的复杂技术任务")
    parser.add_argument("--fixed", action="store_true",
                        help="使用固定计划模式（不做重规划），W5 对照组用")
    args = parser.parse_args()

    print(f"目标:{args.goal}（模式：{'固定' if args.fixed else '自适应'}）\n")

    initial_state = {
        "run_id": uuid.uuid4().hex[:8],
        "user_goal": args.goal,
        "adaptive": not args.fixed,
        "plan": [],
        "current_task": 0,
        "retry_count": 0,          # W4 的重试计数，先把格子铺好
        "replan_count": 0,
        "observations": [],
        "evaluation": None,
        "pending_approval": None,
        "final_answer": "",
    }

    result = build_graph().invoke(initial_state)
    
    print("任务清单")
    for t in result["plan"]:
        print(f"[{t.id}] {t.status} | {t.tool} | {t.description}")

    print(rf"\执行回执:{result['status']}")
    for o in result["observations"]:
        mark = "√" if o.success else "X"
        print(f"  {mark} [{o.task_id}] {o.tool}：{o.error or o.summary[:80]}")
    print("\n========== 最终答案 ==========")
    print(result["final_answer"])
    print(f"\n(运行状态：{result['status']})")

if __name__ == "__main__":
    main()