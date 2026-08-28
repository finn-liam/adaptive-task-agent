import argparse
import uuid

from app.agent.graph import build_graph


def main():
    parser = argparse.ArgumentParser(description="Adaptive Task Planning Agent")
    parser.add_argument("goal",help="要完成的复杂技术任务")
    args = parser.parse_args()

    print(f"目标:{args.goal}\n")

    result = build_graph().invoke({
        "run_id": uuid.uuid4().hex[:8],
        "user_goal": args.goal,
    })

    print("任务清单")
    for t in result["plan"]:
        print(f"[{t.id}] {t.status} | {t.tool} | {t.description}")

    print(rf"\执行回执:{result['status']}")
    for o in result["observations"]:
        mark = "√" if o.success else "X"
        print(f"  {mark} [{o.task_id}] {o.tool}：{o.error or o.summary[:80]}")
    print("\n========== 最终答案 ==========")
    print(result["final_answer"])
    print(f"\n（运行状态：{result['status']}）")

if __name__ == "__main__":
    main()