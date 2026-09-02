"""批量评测 runner：把数据集喂给 Agent，每条 trace 落盘"""

import argparse
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from langgraph.types import Command

from app.agent import llm as llm_mod
from app.agent.graph import build_graph

DATASET = Path("evals/dataset.jsonl")
INIT_KEYS = dict(plan=[], current_task=0, retry_count=0, replan_count=0,
                 observations=[], evaluation=None, pending_approval=None,
                 final_answer="", status="planning")


def invoke_once(payload, config):
    """带审批兜底的单次运行：无人值守时高危任务自动拒绝"""
    result = build_graph().invoke(payload, config)
    for _ in range(3):                          # 最多处理 3 轮审批，防极端死循环
        if not result.get("__interrupt__"):
            return result
        result = build_graph().invoke(
            Command(resume={"approved": False}), config)   # 无人值守 → 自动拒绝
    return result


def run_one(case: dict, mode: str) -> dict:
    run_id = uuid.uuid4().hex[:8]
    t0 = time.monotonic()
    u0 = llm_mod.usage_snapshot()
    payload = {"run_id": run_id, "user_goal": case["input"],
               "adaptive": (mode == "adaptive"), **INIT_KEYS}
    config = {"configurable": {"thread_id": run_id}}

    error = None
    try:
        result = invoke_once(payload, config)
    except Exception as e:                      # noqa: BLE001 —— 单条失败不能拖垮整批
        error = f"{type(e).__name__}: {e}"
        result = {}

    u1 = llm_mod.usage_snapshot()
    obs = result.get("observations", [])
    trace = {
        "case_id": case["id"],
        "mode": mode,
        "run_id": run_id,
        "difficulty": case["difficulty"],
        "type": case["type"],
        "error": error,
        "status": result.get("status", "crashed"),
        "steps": len(obs),
        "replan_count": result.get("replan_count", 0),
        "retry_count": result.get("retry_count", 0),
        "wall_seconds": round(time.monotonic() - t0, 1),
        "tokens": {"input": u1["input"] - u0["input"],
                   "output": u1["output"] - u0["output"]},
        "task_statuses": [{"id": t.id, "status": t.status, "tool": t.tool}
                          for t in result.get("plan", [])],
        "observations": [{"task_id": o.task_id, "tool": o.tool,
                          "success": o.success, "summary": o.summary,
                          "error": o.error} for o in obs],
        "final_answer": result.get("final_answer", ""),
    }
    return trace


def main():
    ap = argparse.ArgumentParser(description="批量评测 runner")
    ap.add_argument("--mode", choices=["fixed", "adaptive"], required=True)
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条（0=全部）")
    ap.add_argument("--offset", type=int, default=0, help="跳过前 N 条（断点续跑用）")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--tag", default="", help="结果目录附加标记")
    args = ap.parse_args()

    cases = [json.loads(l) for l in DATASET.read_text(encoding="utf-8").splitlines() if l.strip()]
    cases = cases[args.offset: args.offset + args.limit if args.limit else None]

    stamp = datetime.now().strftime("%m%d-%H%M")
    outdir = Path(f"results/{stamp}-{args.mode}" + (f"-{args.tag}" if args.tag else ""))
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"评测开始：{len(cases)} 条｜模式 {args.mode}｜并发 {args.workers}｜输出 {outdir}")

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_one, c, args.mode): c for c in cases}
        for fut in as_completed(futures):
            case = futures[fut]
            (outdir / f"{case['id']}.json").write_text(
                json.dumps(fut.result(), ensure_ascii=False, indent=1), encoding="utf-8")
            done += 1
            print(f"  [{done}/{len(cases)}] {case['id']} 完成")

    print(f"✅ 批次结束：{done} 条 trace → {outdir}")


if __name__ == "__main__":
    main()