# W1~W3 全量复盘：每个文件是什么、每个阶段怎么跑

> 本文基于 2026-08-29 的真实代码逐文件撰写。用途：① 自己复习巩固；② 面试前快速回忆；
③ 将来 README「架构设计」章节的底稿。

## 0. 项目全貌（W3 结束时的状态）

```
adaptive-task-agent/
├── main.py                    # 门面：CLI 入口（发车）
├── app/
│   ├── models/
│   │   └── schemas.py         # 数据字典：5 个模型类（全项目唯一的数据定义处）
│   ├── agent/
│   │   ├── llm.py             # 电厂：全项目唯一的模型出口
│   │   ├── planner.py         # 工人①：目标 → 结构化计划（带自愈重试）
│   │   ├── executor.py        # 工人②：取任务 → 交工具 → 回执上白板
│   │   ├── evaluator.py       # 工人③：质检每个任务的执行结果
│   │   ├── replanner.py       # 工人④：根据缺口增量改计划（带熔断）
│   │   ├── final_answer.py    # 工人⑤：汇总回执 → 最终答复
│   │   └── graph.py           # 车间：节点注册 + 边 + 条件路由（只调度不干活）
│   └── tools/
│       ├── registry.py        # 电话簿：名字 → 工具函数
│       ├── base.py            # run_tool：所有工具的公共包装器（安全气囊）
│       ├── read_file.py       # 工具：读本地文件（带越界防御）
│       ├── fetch_url.py       # 工具：抓网页正文（带反爬/类型防御）
│       ├── search_github.py   # 工具：GitHub 搜仓库/拉 README（带限流识别）
│       └── search_web.py      # 工具：全网搜索（Tavily + DuckDuckGo 降级链）
├── tests/                     # 16 个测试全天候站岗（见 §4）
└── docs/                      # devlog / traces / 本文
```

**依赖方向（单向无环，这是架构的核心纪律）**：

```
main.py → graph.py → {planner, executor, evaluator, replanner, final_answer} → llm.py
                                                          ↓
                                        executor → tools(base+registry+各工具)
                          所有节点都读/写 schemas.py 定义的模型；schemas 不依赖任何人
```

**当前完整数据流（W3 版）**：

```
main.py 发车（铺满 12 格初始白板，run_id/user_goal/adaptive...）
  ↓
planner_node ── 调 make_planner()：LLM 生成结构化 Plan（失败自动重试≤3）
  ↓ 写入 plan / current_task=0 / status=executing
executor_node ── 取 plan[current_task] → depends_on 闸门 → run_tool → Observation
  ↓ 写入 observations(+1张) / current_task+1 / plan(任务状态已更新)
evaluator_node ── 拿最新回执 + 任务意图 → LLM 判定 → EvaluationResult
  ↓ 写入 evaluation
route_after_eval（条件边，三岔路）：
  ├─ "replan"（adaptive 且 need_replan 且 replan_count<3）→ replanner_node
  │      └─ 增量改计划（已完成强制保留）→ 写回 plan → 回到 executor
  ├─ "next"（通过 → 干下一个；失败不重规划 → 跳过继续）→ executor_node
  └─ "final"（指针到头，或熔断后无路可走）→ final_answer_node
        └─ 汇总全部回执 → 最终答复（分点+来源+缺失说明）→ status=done → END
```

---

## 1. W1 · 地基周（State + Planner）

**本周目标一句话**：让「一句自然语言」变成「一份结构化、经过校验的任务清单」。

### 1.1 `app/models/schemas.py` —— 数据字典（全项目最重要的文件）

定义了 5 个模型类 + 1 个白板图纸：

| 类 | 职责 | 关键字段 |
|---|---|---|
| `ToolName` | 工具名白名单（Literal 类型），7 个名字一个不能多 | — |
| `TOOL_NAMES` | `get_args(ToolName)` 反推出的字符串元组，供注册表/prompt 复用 | — |
| `Task` | 计划中的单个任务 | `id` / `description` / `tool`（Literal 锁，防 LLM 幻觉工具名）/ `tool_args` / `depends_on` / `status`（默认 pending） |
| `Observation` | 一次工具执行的回执 | `task_id` / `tool` / `success` / `summary`（截断后给 LLM 的内容）/ `error` / `latency_ms` |
| `EvaluationResult` | 质检员的判定书 | `success` / `reason` / `need_replan` / `missing_info`（给重规划器的接力棒） |
| `Plan` | 一次规划的产出 | `reasoning`（规划依据）/ `tasks: list[Task]`（嵌套校验） |
| `AgentState` | 白板图纸（TypedDict，12 格） | 见 §0 数据流；两个特殊格子：`observations` 用 `Annotated[..., operator.add]`（多节点追加不覆盖）、`adaptive` 是 W5 对照实验的开关 |

**设计要点**：
- Pydantic 类只声明字段，**免费获得**：构造时校验、JSON 序列化/反解析、给 LLM 的结构化输出模板；
- `Literal` 是防幻觉的第一道闸门：`tool='bing_search'` 当场抛 ValidationError，报错原文还会喂回给 LLM 帮它自纠；
- TypedDict 和 Pydantic 的分工：**Pydantic 管数据对象的校验（运行时执法），TypedDict 只管函数签名层面的白板形状说明（无运行时开销）**——而且 TypedDict 没有默认值，所以所有格子必须在发车时铺满（W3 的教训）。

### 1.2 `app/agent/llm.py` —— 电厂（14 行，地位极高）

```python
make_llm() → ChatOpenAI(model="deepseek-chat", api_key=环境变量, base_url=DeepSeek地址, temperature=0)
```

- **全项目唯一知道模型是谁的文件**——换供应商/换模型只改这里（决策 D1，你实战演练过 v4-flash）；
- `load_dotenv()` 幂等地把 `.env` 的钥匙读进环境变量；
- `temperature=0`：规划/评估/汇总要的是稳定可复现。

### 1.3 `app/agent/planner.py` —— 第一个工人

三段结构：
1. `PLANNER_PROMPT`：角色设定 + 6 条军规（工具名单插槽 `{tools}`、可执行的 description、3~8 个任务、禁总结类任务、**禁加工类任务**（W3 教训：没有工具能"处理上一步内容"，不教这条 LLM 就幻觉 read_file）、`{goal}` 插槽）；
2. `make_planner()`：闭包里 `llm.with_structured_output(Plan, method="function_calling")`——结构化输出的 function_calling 路线（把 Plan 翻译成"虚拟函数"让模型填参）；
3. `planner(goal)` 内的**自愈循环**：校验失败把 ValidationError 原文拼回 base_prompt 重试，最多 3 次——**每次从干净底稿重拼，不叠错误雪球**。

### 1.4 `app/agent/graph.py`（W1 版）—— 最小车间的雏形

当时只有：`StateGraph(AgentState)` + planner 节点 + `START→planner→END`。核心认知：**节点返回的是"局部更新 dict"，LangGraph 负责合并进白板**。

### 1.5 `main.py` —— 门面

argparse 收 goal（W3 起加 `--fixed` 开关）→ `uuid` 发 run_id → `build_graph().invoke(initial_state)` → 打印任务清单/回执/最终答案。**门面不含任何智能，不知道 LLM 存在**——W6 它会被 FastAPI 无缝替换，这就是分层的好处。

### W1 流程（3 步）

```
CLI 收 goal → planner 花 LLM 调用产出 Plan → 打印任务列表（状态全是 pending）
```

**W1 里程碑**：类型即契约；结构化输出两条路线（json_schema vs function_calling）的兼容性地图。

---

## 2. W2 · 双手周（Tools + Executor 端到端）

**本周目标一句话**：让计划里的每个任务真的被工具执行，回执一张张积累，最后汇总成答案。

### 2.1 `app/tools/registry.py` —— 电话簿

`TOOL_REGISTRY: dict = {"read_file": read_file, ...}`。**名字（字符串键）→ 函数对象（值）**。配套守卫测试保证"注册表 ⊆ 白名单"（决策 D9：白名单=愿景全集，注册表=现役部队，planner 的 prompt 只推销现役的）。

### 2.2 `app/tools/base.py` —— run_tool 公共包装器（全项目的安全气囊）

三步舞：**查电话簿 → 兜住一切意外 → 填统一回执**。

- 查号用 `.get()`：查无此人返回失败的 Observation 而不是抛 KeyError（契约：**包装器外无异常**）；
- `task_id` 是"信封信息"：从 args 里剥出来（否则 `func(**args)` 会收到工具不认识的多余参数）；
- 宽捕获 `except Exception` 是**全项目唯一被允许的地方**（边界哨兵职责，注释必须写明）；
- `_truncate`：超过 head 1200 + tail 400 的正文保留头尾、中间插省略标记（注明真实总长）——W3 质检员判定"README 被截断"的依据就是这行标记；
- `time.monotonic()` 计耗时（不受系统改时间影响）。

### 2.3 四个联网/本地工具（每个都有自己的防御点）

| 文件 | 功能 | 防御点 |
|---|---|---|
| `read_file.py` | 读项目目录内的文本文件 | ① 相对路径以项目根为基准 ② `resolve()` 摊平 `..` 花招 ③ `is_relative_to` 越界拒绝 ④ 不存在 → FileNotFoundError ⑤ 200KB 上限 ⑥ 强制 utf-8（Windows 默认 GBK 的坑） |
| `fetch_url.py` | 抓网页正文 | ① 浏览器 UA（防 403）② 状态码安检 ③ content-type 白名单（html/plain，`startswith` 元组写法）④ 删除 script/style/nav 噪音标签再取正文 ⑤ `<main>`→`<article>`→`<body>` 逐级兜底 ⑥ 正文 <50 字符报警 |
| `search_github.py` | 搜仓库 / 拉 README（一个工具两种 action） | ① PAT 进 Authorization 头（60次/时 → 5000次/时）② `_check` 安检链顺序：先限流(403/429 且报出剩余额度) → 404 → 其他 ③ README 的 base64 解码 |
| `search_web.py` | 全网搜索 | ① Tavily 主通道（POST JSON）② 无 Key 或失败自动降级 DuckDuckGo（延迟导入：只在降级那一刻 import）③ **降级 ≠ 吞错误**：降级原因随结果一起带走（`noqa: BLE001` 豁免 + 注释理由） |

**共同纪律**：工具内部只管"喊干不了"（raise），失败翻译成回执是包装器的事——各司其职。

### 2.4 `app/agent/executor.py` —— 机械臂

流程：取 `plan[current_task]` → depends_on 闸门（有前置没完成 → 该任务标 failed 跳过）→ `run_tool(tool, {**tool_args, "task_id": id})` → 按 `obs.success` 改任务状态 → 返回增量 `{observations:[一张], current_task+1, plan}`。
**失败不停摆**：一个坏任务只标 failed，指针照常前移（后续处置交给 W3 的评估路由）。

### 2.5 `app/agent/final_answer.py` —— 汇总出口

把全部回执拼成"任务X（工具Y）：内容/失败原因"的观察资料块 → LLM 生成最终答复。Prompt 四要求：分点、只依据资料、**明确说明缺失**、附参考来源。这是全项目第二次（每次运行中第三次）LLM 调用。

### 2.6 graph.py 升级 + 循环边

新增 executor 节点和**条件边**：路由函数返回钥匙（`"continue"`/`"done"`），映射表把钥匙翻译成目的地——指针没走完就回 executor 自己，走完了去 final_answer。

### W2 流程

```
goal → planner 出计划 → executor 干 task1 → 路由 → executor 干 task2 → … → 全干完
     → final_answer 汇总 → 最终答案（CLI 全程可见每个任务的 √/X 和耗时）
```

**W2 里程碑**：端到端闭环（6/6 任务全绿首次达成）；简历第一句真话："Agent 可自主完成多步网络研究任务"。

---

## 3. W3 · 灵魂周（Evaluator + Re-planning）

**本周目标一句话**：让计划可以被执行证据修改——但要在保险丝保护下改。

### 3.1 `app/agent/evaluator.py` —— 质检员

- 只验"刚出炉的那张回执"：`observations[-1]` + 按 task_id 找到对应任务；
- 判定标准写进 prompt：**"不是工具没报错就叫成功"**——导航菜单、报错页、截断的内容都不算；
- 输出 `EvaluationResult`（结构化），其中 `missing_info` 是给重规划器的接力棒：不只说"不行"，还说清"缺什么"；
- 已知局限（W5 会处理）：判定尺度在多次运行间会漂移（同一截断场景一次判重规划一次判通过）→ 用温度 0 + 结构化判据 + 人工校准收敛。

### 3.2 `app/agent/replanner.py` —— 计划改写者（灵魂部件）

- 输入：总目标 + 战况表（✔/X/o 逐任务一行）+ 质检判定 + 缺口；
- 输出：完整的**修改后计划**（结构化 Plan）；
- **三条纪律，prompt 和代码双重执行**：
  1. 已完成任务强制保留——代码层用 `old_status` 存档逐个核对，**不信 LLM 的记性**；
  2. 其余任务（失败/新增/被改）一律重置 pending——同样的代码卫生化原则；
  3. `current_task` 重置到第一个 pending（用带兜底的 `next()`；极端情况下强制重置刚失败的任务）；
- 每次重规划 `replan_count + 1`，路由层 `replan_count < 3` 熔断（R5 风险对策，已实战验证过一次完整熔断）。

### 3.3 graph.py 再升级 + main.py 开关

- evaluator 进图：`executor → evaluator` 必经边；条件边挂 evaluator 后面，三岔路 `next / replan / final`；
- **路由分支顺序是设计**（W3 实战修正过规格 bug）："需要重规划"优先于"跑完了"——先填缺口，再谈收工；
- replanner 的出口是**无条件边**回 executor（重规划完必然继续干活）；evaluator 的出口**只有**条件边（一个出口只能有一种管理方式——固定边+条件边并存会导致并行触发的事故）；
- main.py：`--fixed` 开关 → `adaptive: not args.fixed` 进白板；初始白板**铺满 12 格**（TypedDict 无默认值，读未写过的格子就是 KeyError——LangGraph 新手事故榜第一名）。

### 3.4 W3 完整流程（对照 §0 的图）

每个任务执行后必过质检；质检说"缺信息"时：自适应模式 → 重规划改计划 → 回去执行新任务；固定模式 → 装聋跳过（这就是 W5 对照实验的唯一变量）。三次熔断后带着诚实缺口降级作答。

**W3 里程碑**：对照实验 trace ×2 归档（Fixed 全任务成功却整体失败 vs Adaptive 9 来源闭环）；面试核心叙事成形——"计划可以被证据修改，且知道什么时候停"。

---

## 4. tests/ 清单（16 个测试）

| 文件 | 测什么 |
|---|---|
| test_models.py (5) | 四个数据模型：合法构造 / 非法工具名拒绝 / 默认值 / 嵌套校验 / 序列化往返 |
| test_read_file.py (4) | 正常读取 + 越界拒绝 + 不存在拒绝 + 绝对路径越界拒绝 |
| test_fetch_url.py (3) | respx 假网络：正文抽取 / 404 抛错 / 非 HTML 拒绝 |
| test_search_github.py (3) | respx 假 JSON：结果格式化 / base64 解码 / 限流报错 |
| test_registry.py (1) | 守卫：注册表 ⊆ 白名单（"写了忘挂载"秒级变红） |

测试的本质：**把当年在终端手工验证过的行为，翻译成机器语言永久固化**。

## 5. 复盘中发现的问题（已修/待修）

- [x] replanner.py 返回键 `"plam"` → `"plan"`（已修）
- [ ] **executor.py 第 25 行**：depends_on 闸门分支返回 `"observation"`（单数）→ 应为 `"observations"`——至今未触发过的潜伏 bug，闸门一响回执就会静默丢失
- [ ] 复盘本文时确认的小瑕疵：devlog 里 "AgentState十一份带数据类型的说明书" 应为"是一份"；planner 失败文案"放弃治疗"风格偏随意（无伤大雅，看你要不要改）
