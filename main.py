"""命令行入口：既能发新车，也能用 run_id 把断掉的旧车原地复活

W4-2 新增：
- 每次运行都带 thread_id（=run_id）发车，LangGraph 自动把白板快照存进 checkpoints.sqlite；
- --resume RUN_ID：不给新输入（invoke(None)），LangGraph 从该 run 的最近快照继续跑。
"""

import argparse
import uuid

from app.agent.graph import build_graph


def main():
    parser = argparse.ArgumentParser(description="Adaptive Task Planning Agent")
    parser.add_argument("goal", nargs="?", default="",
                        help="要完成的复杂技术任务（--resume 恢复模式可省略）")
    parser.add_argument("--fixed", action="store_true",
                        help="使用固定计划模式（不做重规划），W5 对照组用")
    parser.add_argument("--resume", metavar="RUN_ID",
                        help="从断点恢复指定的 run（用当时打印的 run_id）")
    args = parser.parse_args()

    if args.resume:
        # —— 续跑路线 ——
        # invoke 的第一个参数是 None = "不给新输入"；
        # LangGraph 查到该 thread 的最近快照，从断掉的节点继续（节点级"至少一次"语义）
        run_id = args.resume
        print(f"🔄 恢复 run {run_id}……\n")
        result = build_graph().invoke(None, {"configurable": {"thread_id": run_id}})
    else:
        # —— 新车路线 ——
        if not args.goal:
            parser.error("新运行必须提供目标，例如：uv run python main.py \"你的目标\"")
        print(f"目标:{args.goal}（模式：{'固定' if args.fixed else '自适应'}）\n")
        run_id = uuid.uuid4().hex[:8]
        print(f"（本次 run_id：{run_id}，中断后可用 --resume {run_id} 复活）")
        initial_state = {
            "run_id": run_id,          # 必须和 thread_id 同源！快照归属全靠它对上号
            "user_goal": args.goal,
            "adaptive": not args.fixed,
            "plan": [],
            "current_task": 0,
            "retry_count": 0,
            "replan_count": 0,
            "observations": [],
            "evaluation": None,
            "pending_approval": None,
            "final_answer": "",
            "status": "planning",
        }
        # config 里的 thread_id 就是快照的"档案柜编号"，两种路线都必须携带
        result = build_graph().invoke(initial_state,
                                      {"configurable": {"thread_id": run_id}})

    print("任务清单")
    for t in result["plan"]:
        print(f"[{t.id}] {t.status} | {t.tool} | {t.description}")

    print(f"执行回执（共 {len(result['observations'])} 张）")
    for o in result["observations"]:
        mark = "√" if o.success else "X"
        print(f"  {mark} [{o.task_id}] {o.tool}：{o.error or o.summary[:80]}")

    print("\n========== 最终答案 ==========")
    print(result["final_answer"])
    print(f"\n(运行状态：{result['status']}｜run_id：{run_id})")


if __name__ == "__main__":
    main()
