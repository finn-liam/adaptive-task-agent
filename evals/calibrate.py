"""人工校准：盲测抽样 → 人工判卷 → 对账一致率（W5-4）"""

import argparse
import json
import random
import re
from datetime import datetime
from pathlib import Path

DATASET = Path("evals/dataset.jsonl")
CALIB_DIR = Path("results/calibration")
SHEET = CALIB_DIR / "grading_sheet_blind.md"
KEY = CALIB_DIR / "blind_key.json"
REPORT = CALIB_DIR / "report.md"


def _load_dataset():
    return {c["id"]: c for c in
            (json.loads(l) for l in DATASET.read_text(encoding="utf-8").splitlines() if l.strip())}


def _load_all_judged(results_root="results"):
    items = []
    for d in sorted(Path(results_root).iterdir()):
        jd = d / "judged"
        if not d.is_dir():
            continue
        for f in jd.glob("*.json"):
            v = json.loads(f.read_text(encoding="utf-8"))
            t = json.loads((d / f.name).read_text(encoding="utf-8"))
            items.append((d.name, v, t))
    return items


def make_sample(n: int, only_fails: bool = False):
    dataset = _load_dataset()
    items = _load_all_judged()
    random.seed(2026)                        # 新种子：和上一轮（42）样本不重叠同分布
    if only_fails:
        fails = [it for it in items if not it[1]["success"]]
        oks = [it for it in items if it[1]["success"]]
        random.shuffle(oks)                  # 对照组：成功案例打乱后混入
        samples = fails + oks[: max(0, n - len(fails))]
        random.shuffle(samples)              # 混洗顺序，看不出哪些是 judge 判败的
    else:
        samples = random.sample(items, n)

    CALIB_DIR.mkdir(parents=True, exist_ok=True)
    key = {}
    with SHEET.open("w", encoding="utf-8") as w:
        w.write("# W5-4 人工判卷表（盲测版：不含 judge 判定，凭自己判断勾选）\n\n"
                "逐条把「你的判定」中一格 [ ] 改成 [x]（只勾一个）。\n\n")
        for i, (dir_name, v, t) in enumerate(samples, 1):
            case = dataset[v["case_id"]]
            key[str(i)] = {"case_id": v["case_id"], "dir": dir_name,
                           "judge_success": v["success"], "judge_coverage": v["coverage"]}
            w.write(f"## {i:02d} · {v['case_id']}\n\n")
            w.write(f"**题目**：{case['input']}\n\n")
            w.write("**评分要点**：\n")
            for p in case["rubric"]:
                w.write(f"- {p}\n")
            w.write(f"\n**答卷节选**：\n\n> {(t.get('final_answer') or '')[:1500]}\n\n")
            w.write("**你的判定**：[ ] 成功  [ ] 失败\n\n")
            w.write("**备注**：\n\n---\n\n")
    KEY.write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"盲测判卷表已生成：{SHEET}（{n} 份，judge 判定已隐藏）\n"
          f"勾完后运行：uv run python -m evals.calibrate score")


def score():
    content = SHEET.read_text(encoding="utf-8")
    key = {int(k): v for k, v in json.loads(KEY.read_text(encoding="utf-8")).items()}
    sections = re.split(r"\n(?=## \d+ · )", content)[1:]
    rows, problems = [], []
    for sec in sections:
        m = re.match(r"## (\d+) · (\S+)", sec)
        if not m:
            continue
        idx, case_id = int(m.group(1)), m.group(2)
        mark = re.search(r"\*\*你的判定\*\*：\[([ xX])\] 成功\s+\[([ xX])\] 失败", sec)
        if mark is None or (mark.group(1) == "x") == (mark.group(2) == "x"):
            problems.append(case_id)
            continue
        k = key[idx]
        notes = re.search(r"\*\*备注\*\*：\n?(.*)", sec, re.DOTALL)
        rows.append({"idx": idx, "case_id": case_id, "dir": k["dir"],
                     "judge_success": k["judge_success"],
                     "judge_coverage": k["judge_coverage"],
                     "human_success": mark.group(1) == "x",
                     "human_notes": (notes.group(1).strip().splitlines() or [""])[0] if notes else ""})

    if problems:
        print(f"以下 {len(problems)} 条没勾或勾了两格：{problems}")
        return
    if len(rows) != len(key):
        print(f"只填了 {len(rows)}/{len(key)} 条，补完再跑")
        return

    agree = [r for r in rows if r["human_success"] == r["judge_success"]]
    dis = [r for r in rows if r["human_success"] != r["judge_success"]]
    rate = len(agree) / len(rows)

    print(f"\n===== 盲测校准报告（{datetime.now().astimezone().strftime('%Y-%m-%d')}）=====")
    print(f"样本：{len(rows)} 份（种子 2026，judge 判定隐藏）")
    print(f"人机一致率：{len(agree)}/{len(rows)} = {rate:.0%}")
    print(f"门槛 80%：{'✅ 达标，judge 可信' if rate >= 0.8 else '❌ 未达标，需修 judge 后重新校准'}")
    if dis:
        print("\n分歧清单（人工 vs judge）：")
        for r in dis:
            print(f"  {r['case_id']}（{r['dir']}）: 人工={'成功' if r['human_success'] else '失败'} "
                  f"judge={'成功' if r['judge_success'] else '失败'}"
                  f"（覆盖率 {r['judge_coverage']}）｜{r['human_notes'] or '无备注'}")

    with REPORT.open("w", encoding="utf-8") as w:
        w.write(f"# W5-4 人工校准报告（盲测版）\n\n- 样本：{len(rows)}（种子 2026，judge 判定对阅卷人隐藏）\n"
                f"- 人机一致率：{len(agree)}/{len(rows)} = {rate:.0%}\n"
                f"- 门槛 80%：{'达标' if rate >= 0.8 else '未达标'}\n"
                f"- 说明：首版校准表暴露 judge 判定导致锚定偏误，改用盲测重校。\n")
        for r in dis:
            w.write(f"\n## 分歧 {r['case_id']}（{r['dir']}）\n\n"
                    f"- 人工判定：{'成功' if r['human_success'] else '失败'}\n"
                    f"- judge 判定：{'成功' if r['judge_success'] else '失败'}"
                    f"（覆盖率 {r['judge_coverage']}）\n- 人工备注：{r['human_notes'] or '无'}\n")
    print(f"\n报告已写入：{REPORT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="W5-4 人工校准（盲测）")
    ap.add_argument("command", choices=["make", "score"])
    ap.add_argument("--n", type=int, default=15)
    ap.add_argument("--only-fails", action="store_true",
                    help="定向抽取 judge 判失败的案例（混入少量成功作对照）")
    args = ap.parse_args()
    if args.command == "make":
        make_sample(args.n, args.only_fails)
    else:
        score()