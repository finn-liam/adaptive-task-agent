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
        print(f"{t.id}状态={t.status} 工具={t.tool}")
        print(f"{t.description}")

    print(f"\n运行状态:{result['status']}")

if __name__ == "__main__":
    main()