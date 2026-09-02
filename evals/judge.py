"""LLM-as-judge：对照 rubric 给每份 trace 的最终答卷打覆盖率分"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.agent.llm import make_llm

DATASET = Path("evals/dataset.jsonl")


class Point(BaseModel):
    point: str                       # 对应的评分要点
    hit: bool                        # 是否命中
    evidence: str                    # 判定依据（答卷原句或"未见相关内容"）


class JudgeVerdict(BaseModel):
    points: list[Point]
    notes: str = ""


JUDGE_PROMPT = """你是严格的阅卷老师。根据评分要点，逐条判定 Agent 的答卷是否命中。

【题目】{input}

【评分要点】（必须逐条给出判定，一条都不许漏）
{rubric}

【Agent 答卷】
{answer}

判定规则：
1. 只依据答卷内容判定；答卷中没有相关内容 → hit=false；
2. 措辞不同但语义命中 → hit=true（不要逐字苛求）；
3. 答卷明确承认失败/缺失的要点 → hit=false；
4. evidence 一句话写明依据（引用答卷原句，或写"未见相关内容"）。
"""


def judge_one(trace: dict, case: dict) -> dict:
    answer = trace.get("final_answer") or ""
    if trace.get("error") or not answer:
        return {"case_id": trace["case_id"], "mode": trace["mode"],
                "coverage": 0.0, "success": False, "points": [],
                "notes": f"跳过判卷：{'崩溃 ' + str(trace['error']) if trace.get('error') else '无最终答案'}"}

    rubric_text = "\n".join(f"{i}. {p}" for i, p in enumerate(case["rubric"], 1))
    prompt = (JUDGE_PROMPT
              .replace("{input}", case["input"])
              .replace("{rubric}", rubric_text)
              .replace("{answer}", answer[:6000]))

    for attempt in range(3):
        try:
            verdict = make_llm().with_structured_output(
                JudgeVerdict, method="function_calling").invoke(prompt)
            if verdict is None or verdict.points is None:
                raise ValueError("模型未返回结构化判定（可能输出了普通文本）")
            hits = sum(1 for p in verdict.points if p.hit)
            coverage = hits / len(case["rubric"]) if case["rubric"] else 0.0
            return {"case_id": trace["case_id"], "mode": trace["mode"],
                    "coverage": round(coverage, 3),
                    "success": coverage >= 0.6,
                    "points": [p.model_dump() for p in verdict.points],
                    "notes": verdict.notes}
        except (ValidationError, ValueError) as e:
            prompt += (f"\n\n你上一次的输出不合法：{e}\n"
                       "请严格按每个评分要点逐条输出 points，修正后重新判卷。")
    return {"case_id": trace["case_id"], "mode": trace["mode"],
            "coverage": 0.0, "success": False, "points": [],
            "notes": "judge 连续 3 次输出不合法"}


def main():
    ap = argparse.ArgumentParser(description="LLM-as-judge 阅卷器")
    ap.add_argument("--results-dir", required=True, help="要判卷的结果目录")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()

    rdir = Path(args.results_dir)
    dataset = {c["id"]: c for c in
               (json.loads(l) for l in DATASET.read_text(encoding="utf-8").splitlines() if l.strip())}
    outdir = rdir / "judged"
    outdir.mkdir(exist_ok=True)

    traces = []
    for f in sorted(rdir.glob("*.json")):
        if (outdir / f.name).exists():          # 断点续判：判过的跳过
            continue
        t = json.loads(f.read_text(encoding="utf-8"))
        if t["case_id"] in dataset:
            traces.append(t)
    if args.limit:
        traces = traces[:args.limit]
    print(f"判卷开始：{len(traces)} 份答卷 → {outdir}")

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(judge_one, t, dataset[t["case_id"]]): t for t in traces}
        for fut in as_completed(futures):
            verdict = fut.result()
            (outdir / f"{verdict['case_id']}.json").write_text(
                json.dumps(verdict, ensure_ascii=False, indent=1), encoding="utf-8")
            done += 1
            mark = "✅" if verdict["success"] else "❌"
            print(f"  [{done}/{len(traces)}] {mark} {verdict['case_id']} 覆盖率 {verdict['coverage']}")

    print(f"✅ 判卷结束：{done} 份判定 → {outdir}")


if __name__ == "__main__":
    main()