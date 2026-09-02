"""W5-5 指标汇总：聚合 4 个结果目录，产出 docs/experiments.md"""

import json
import statistics
from pathlib import Path

PASSES = {
    "adaptive": ["results/0901-2008-adaptive-full1", "results/0901-2203-adaptive-full2"],
    "fixed": ["results/0901-2034-fixed-full1", "results/0901-2240-fixed-full2"],
}
PRICE = {"in": 1.5, "out": 4.5}          # v4-flash 空闲时段价（元/百万 tokens）


def load_pass(dirs):
    rows = []
    for d in dirs:
        d = Path(d)
        for f in sorted(d.glob("*.json")):
            t = json.loads(f.read_text(encoding="utf-8"))
            jf = d / "judged" / f.name
            j = (json.loads(jf.read_text(encoding="utf-8"))
                 if jf.exists() else {"success": False, "coverage": 0.0})
            plan = t.get("task_statuses", [])
            done = sum(1 for p in plan if p["status"] == "completed")
            obs = t.get("observations", [])
            rows.append({"case_id": t["case_id"],
                         "success": bool(j.get("success")),
                         "plan_completion": (done / len(plan)) if plan else 0.0,
                         "tool_calls": len(obs),
                         "tool_ok": sum(1 for o in obs if o["success"]),
                         "steps": t.get("steps", 0),
                         "retry": t.get("retry_count", 0),
                         "replan": t.get("replan_count", 0),
                         "wall": t.get("wall_seconds", 0),
                         "tin": t["tokens"]["input"], "tout": t["tokens"]["output"],
                         "difficulty": t.get("difficulty", "?"),
                         "type": t.get("type", "?")})
    return rows


def metrics(rows):
    n = len(rows)
    calls = sum(r["tool_calls"] for r in rows)
    return {"runs": n,
            "success_rate": sum(r["success"] for r in rows) / n,
            "plan_completion": sum(r["plan_completion"] for r in rows) / n,
            "tool_accuracy": (sum(r["tool_ok"] for r in rows) / calls) if calls else 0.0,
            "retry_rate": sum(1 for r in rows if r["retry"] > 0) / n,
            "replan_rate": sum(1 for r in rows if r["replan"] > 0) / n,
            "avg_steps": sum(r["steps"] for r in rows) / n,
            "avg_latency": sum(r["wall"] for r in rows) / n,
            "tokens_per_run": sum(r["tin"] + r["tout"] for r in rows) / n,
            "cost": (sum(r["tin"] for r in rows) / 1e6 * PRICE["in"]
                     + sum(r["tout"] for r in rows) / 1e6 * PRICE["out"])}


def main():
    per_mode = {}
    for mode, dirs in PASSES.items():
        p1, p2 = metrics(load_pass(dirs[:1])), metrics(load_pass(dirs[1:]))
        avg = {k: statistics.mean([p1[k], p2[k]]) for k in p1}
        per_mode[mode] = {"pass1": p1, "pass2": p2, "avg": avg}
        print(f"{mode}: pass1 成功率 {p1['success_rate']:.0%}｜pass2 {p2['success_rate']:.0%}"
              f"｜两遍均值 {avg['success_rate']:.0%}")

    a, f = per_mode["adaptive"]["avg"], per_mode["fixed"]["avg"]
    lift = (a["success_rate"] - f["success_rate"]) * 100
    cost_ratio = a["cost"] / f["cost"] if f["cost"] else 0

    lines = [
        "# W5 评测报告：Fixed vs Adaptive Planning",
        "",
        "- 模型：deepseek-chat（服务端实测回显 DeepSeek-V4-Flash 非思考模式）",
        "- 数据集：100 条（3 类任务 × 3 难度，含 13 道必败/对抗题）",
        "- 每种模式各跑 2 遍取均值；judge 为同模型 rubric 覆盖率法（阈值 0.6），",
        "  经 20 份盲测人工校准，一致率 85%（≥80% 门槛）",
        "",
        "## 主对比表（两遍均值）",
        "",
        "| 指标 | Fixed | Adaptive | 差异 |",
        "|---|---|---|---|",
        f"| Task Success Rate | {f['success_rate']:.0%} | {a['success_rate']:.0%} | **{lift:+.0f}pp** |",
        f"| Tool Call Accuracy | {f['tool_accuracy']:.0%} | {a['tool_accuracy']:.0%} | — |",
        f"| Plan Completion Rate | {f['plan_completion']:.0%} | {a['plan_completion']:.0%} | — |",
        f"| Retry Rate（含重试的 run 占比） | {f['retry_rate']:.0%} | {a['retry_rate']:.0%} | — |",
        f"| Re-plan Rate | {f['replan_rate']:.0%} | {a['replan_rate']:.0%} | — |",
        f"| Avg Steps | {f['avg_steps']:.1f} | {a['avg_steps']:.1f} | — |",
        f"| Avg Latency | {f['avg_latency']:.0f}s | {a['avg_latency']:.0f}s | — |",
        f"| Tokens/run | {f['tokens_per_run']:.0f} | {a['tokens_per_run']:.0f} | — |",
        f"| 单遍成本（空闲价估算） | ¥{f['cost']:.1f} | ¥{a['cost']:.1f} | {cost_ratio:.2f}x |",
        "",
        "## 难度分层成功率",
        "",
        "| 难度 | Fixed | Adaptive |",
        "|---|---|---|---|",
    ]
    arows = load_pass(PASSES["adaptive"]); frows = load_pass(PASSES["fixed"])
    for diff in ("easy", "medium", "hard"):
        am = [r for r in arows if r["difficulty"] == diff]
        fm = [r for r in frows if r["difficulty"] == diff]
        lines.append(f"| {diff} | {sum(r['success'] for r in fm)/len(fm):.0%} "
                     f"| {sum(r['success'] for r in am)/len(am):.0%} |")
    lines += ["", "## 判定为失败的案例（Adaptive 两遍均失败）", ""]
    a_by_id = {}
    for r in arows: a_by_id.setdefault(r["case_id"], []).append(r["success"])
    for cid, res in sorted(a_by_id.items()):
        if not any(res):
            lines.append(f"- {cid}")
    lines += ["", "## 人工校准（盲测）", ""]
    cal = Path("results/calibration/report.md")
    if cal.exists():
        lines += cal.read_text(encoding="utf-8").splitlines()
    Path("docs").mkdir(exist_ok=True)
    Path("docs/experiments.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n报告已写入：docs/experiments.md")


if __name__ == "__main__":
    main()