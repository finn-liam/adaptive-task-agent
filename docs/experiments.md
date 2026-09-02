# W5 评测报告：Fixed vs Adaptive Planning

- 模型：deepseek-chat（服务端实测回显 DeepSeek-V4-Flash 非思考模式）
- 数据集：100 条（3 类任务 × 3 难度，含 13 道必败/对抗题）
- 每种模式各跑 2 遍取均值；judge 为同模型 rubric 覆盖率法（阈值 0.6），
  经 20 份盲测人工校准，一致率 85%（≥80% 门槛）

## 主对比表（两遍均值）

| 指标 | Fixed | Adaptive | 差异 |
|---|---|---|---|
| Task Success Rate | 96% | 97% | **+1pp** |
| Tool Call Accuracy | 89% | 87% | — |
| Plan Completion Rate | 87% | 92% | — |
| Retry Rate（含重试的 run 占比） | 0% | 0% | — |
| Re-plan Rate | 0% | 48% | — |
| Avg Steps | 4.8 | 6.7 | — |
| Avg Latency | 37s | 47s | — |
| Tokens/run | 27967 | 43655 | — |
| 单遍成本（空闲价估算） | ¥6.0 | ¥9.5 | 1.59x |

## 难度分层成功率

| 难度 | Fixed | Adaptive |
|---|---|---|---|
| easy | 100% | 98% |
| medium | 97% | 100% |
| hard | 91% | 91% |

## 判定为失败的案例（Adaptive 两遍均失败）


## 人工校准（盲测）

# W5-4 人工校准报告（盲测版）

- 样本：20（种子 2026，judge 判定对阅卷人隐藏）
- 人机一致率：17/20 = 85%
- 门槛 80%：达标
- 说明：首版校准表暴露 judge 判定导致锚定偏误，改用盲测重校。

## 分歧 lp-h7（0901-2240-fixed-full2）

- 人工判定：成功
- judge 判定：失败（覆盖率 0.333）
- 人工备注：---

## 分歧 gh-e7（0901-2034-fixed-full1）

- 人工判定：成功
- judge 判定：失败（覆盖率 0.333）
- 人工备注：---

## 分歧 gh-e5（0901-2008-adaptive-full1）

- 人工判定：成功
- judge 判定：失败（覆盖率 0.333）
- 人工备注：---
