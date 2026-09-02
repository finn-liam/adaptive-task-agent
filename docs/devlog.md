# W1做了什么我之前不知道的：

pyproject.toml：项目的“身份证”，记录项目名、要求的 Python 版本、依赖清单。它是行业标准格式（取代了旧的 requirements.txt + setup.py 双文件时代）
知道了github除了通过git来提交仓库代码还可以通过github_token令牌来配置.env环境中可以做到：search_github工具调用github官方接口时出示，把限速从60次/小时升到了5000次/小时
uv run ruff check .        ：确认检查器真的能工作，配置真的能读到。

新学了一种表示数据结构的展示：
source_url: str | None = None
└───名字───┘ └─类型─┘ └默认值┘

assert的作用：Python 自带的语句，语义一句话：“我断言这个条件为真；如果它是假的，立刻爆炸（抛 AssertionError）

deepseek新模型自动开启思考模式，使用function calling来达到平衡

DeepSeek 返回一段 JSON
   ↓  with_structured_output 自动反序列化+校验
Plan 对象（Pydantic 实例，只是个局部变量，活在 planner_node 函数体内）
   ↓  .tasks 取出其中的字段（就是我们定义过的 list[Task]）
{"plan": plan.tasks, ...}          ← 节点交出的"增量更新单"
   ↓  LangGraph 把它写进白板的 plan 格子
AgentState["plan"]                 ← 从此刻起，它住在白板上
   ↓  invoke() 全图跑完，返回白板的最终快照
r['plan']                          ← 你命令行里打印的那份

class Task(Basemodel):继承，领养了BaseModel的全部能力：校验引擎，序列化方法，再在上面声明自己的字段。

在哪卡过：不同文件之间来传递参数变量或者是函数，真正理解起来得看每一个导入的模块
怎么解的：理解每一个模块的参数和输出
补充：pydantic这个模块得学习一遍


# W2
再原来基础的langgraph中补充了现在知道

state可以当作是一块白板，在流程中穿梭。AgentState十一份带数据类型的说明书，按照给的字段才能使用。
比如在代码中：def executor_node(state: AgentState) -> dict:

g.compile() 函数的作用是产出可运行的图纸。

新学到了单元测试，通过python中的pytest库来做一个单元测试，
pytest干的事情：进入tests/文件夹，找出所有文件名test_开头的py文件，把里面所有的函数名test_k开头的函数，一个一个替你调用

需要自己把流程图给说一遍，下面的详细线路图是没有final_answer节点的，明天复述的时候记得补充。

## 标准答案：
你敲：uv run python main.py "搜索 langgraph 的 GitHub 仓库，阅读它的 README，再找入门教程"
│
├─【阶段 0 · 启动】main.py
│   1. main() 启动
│   2. argparse: parse_args() → args.goal = 你的那句话
│   3. uuid.uuid4().hex[:8] → run_id（如 "a3f21c"）
│   4. build_graph()（graph.py）
│   │    StateGraph(AgentState)        ← 按图纸准备白板管理器
│   │    add_node("planner", …)        ← 登记两个工人
│   │    add_node("executor", …)
│   │    add_edge(START,"planner")     ← 拉直线边
│   │    add_edge("planner","executor")
│   │    add_conditional_edges("executor", route_after_executor, {…})  ← 挂循环路由
│   │    .compile()                    ← 产出"可执行图"
│   5. graph.invoke({"run_id":…, "user_goal":…})   ★ 总开关
│        LangGraph 内部：按说明书补全白板所有格子（plan=[]、current_task=0、observations=[]…）
│        查边 → START 的下一站是 planner
│
├─【阶段 1 · 规划】planner_node(state)（graph.py 里的壳）
│   6. print "📐 正在拆解……"
│   7. make_planner()(state["user_goal"]) 拆成两步：
│      (a) make_planner()（planner.py）
│      │    make_llm()（llm.py）：load_dotenv() → os.environ 取 DEEPSEEK_API_KEY
│      │              → 造 ChatOpenAI 实例（此刻还没联网，只是把"电话"造好）
│      │    with_structured_output(Plan, method="function_calling")
│      │              → 造出"会逼模型按 Plan 填表"的新对象
│      (b) planner(goal) 真正执行：
│           prompt = 军规.replace("{tools}", ", ".join(TOOL_REGISTRY))   ← 现役 4 工具名单
│                          .replace("{goal}", goal)
│           structured_llm.invoke(prompt)：
│              LangChain 把 Plan 翻译成"函数说明书" → httpx POST api.deepseek.com
│              （★ 第一次花钱的网络往返，约 2~5 秒）
│              DeepSeek 回传 JSON → 交给 Plan.model_validate（schemas.py 质检）
│                 ├─ 不合格 → ValidationError → except 分支：报错拼回 prompt → 重试（最多3次）
│                 └─ 合格 → 得到 Plan 对象
│   8. planner_node 交回 {"plan": plan.tasks, "current_task": 0, "status": "executing"}
│      LangGraph 合并 → 白板这三个格子被写入
│
├─【阶段 2】直线边 → 下一站 executor。LangGraph 把【最新版白板】递给 executor_node
│
├─【阶段 3 · 干活】executor_node(state)（executor.py）—— 每个任务走一遍本段
│   9.  plan=state["plan"]；idx=0；task=plan[0]（t1）→ print ⚙️
│   10. depends_on 闸门（V1 基本直通）
│   11. run_tool("search_github", {"task_id":"t1", …参数})（base.py）
│   │    TOOL_REGISTRY.get("search_github")     ← 电话簿查号
│   │    剥离 task_id → clean_args
│   │    func(**clean_args) → search_github.py：
│   │       _headers()：load_dotenv + 取 GITHUB_TOKEN → 组装请求头
│   │       httpx.get(api.github.com/search/repositories…)  ← 真网络（免费）
│   │       _check(resp)：状态码安检 → resp.json()
│   │       格式化 → 返回结果字符串
│   │    收口：构造 Observation（summary 截断、latency 计时）
│   12. task.status = "completed" / "failed"     ← 直接改白板上那个任务对象
│   13. 交回 {"observations":[一张回执], "current_task":1, "plan":plan}
│        LangGraph 合并：observations 走 operator.add → 追加不覆盖
│
├─【阶段 4 · 路由判断】route_after_executor(state)（拿到最新白板）
│   14. current_task(1) < len(plan)(3) → 返回 "continue" → 下一站还是 executor
│   15. 回到阶段 3 执行 t2 → 路由 → 执行 t3 → 路由
│   16. t3 之后：current_task(3) >= 3 → "done" → END，图停机
│
└─【阶段 5 · 收官】main.py
    17. invoke 返回【最终白板】= result
    18. 打印 result["plan"]（各任务状态）+ result["observations"]（回执列表）



白板诞生            current_task = 0
planner 跑完        current_task = 0（再写一遍）
executor 干 task1   开工时读 idx=0 → 取 plan[0] → 干完返回 idx+1
                    current_task = 1
route_after_eval    读它：1 < 3 → 没走完 → 回 executor
executor 干 task2   开工时读 idx=1 → 取 plan[1] → 干完
                    current_task = 2
executor 干 task3   开工时读 idx=2 → 取 plan[2] → 干完
                    current_task = 3
route_after_eval    读它：3 >= 3 → 走完了 → final

# W3 对照实验（traces 存在 docs/traces/ 下）

同一个目标："抓取 runoob 的 LangGraph quick-start 页面，总结其中 Checkpoint 持久化机制的完整章节"

## 两种模式的对比结论

| | Fixed 模式 | Adaptive 模式 |
|---|---|---|
| 计划 | 只有 1 个任务：抓目标页 | 3 个任务：抓页 + 两路关键词搜索 |
| 任务完成率 | 1/1，全部"成功" | 3/3，全部成功 |
| 最终答案 | 死胡同："无法获取 Checkpoint 内容"，只有 1 条来源 | 给出了 Checkpoint 机制要点（快照/重播/Store/多后端），9 条来源 |

最重要的结论：**Fixed 模式所有任务都成功了，但整个任务失败了**——
这说明"计划完成率高"和"任务真正成功"是两回事，W5 评测要分开统计这两个指标的原因就在这。
Fixed 的问题不是执行不行，是计划一开始就没铺够，而且中途没有任何补救机会。

## 本周卡得最久的坑：plam（写下来防再犯）

症状：重规划后 executor 报 IndexError: list index out of range。
排查：报错指向 plan[idx]，idx 来自 replanner 返回的 current_task。
根因：replanner 返回字典的键写成了 "plam"——LangGraph 只认 "plan"，
于是新计划从来没写上白板，current_task 却是按新计划（7个任务）算的下标，
拿去旧计划（4个任务）里取，直接越界。
修法：改键名 + 给 current_task 的计算加兜底（找不到 pending 时强制重置刚失败的任务）。
教训：返回字典的键是和白板的"合同"，拼错不报错、只是静默不生效，比崩溃更难查。

另一个反复出现的根因（出现了三次）：**LLM 给的状态标记不可信，必须在代码层卫生化**——
已完成保留、其余一律重置 pending。prompt 负责引导，代码负责兜底。

## 面试问答演练（我自己答一遍）

问：你的 Re-planner 怎么防止死循环？
答：三层保险。第一，replan_count 熔断，最多重规划 3 次，超过就降级作答（我在测试里真的见过：
一次运行里 replanner 连续 3 次没修好坏任务，第 4 次想重规划被路由拒绝，带着诚实缺口收尾）；
第二，单 run 步数上限；第三，重规划约束只允许新增/修改未完成任务，已完成的强制保留，
计划不会越改越大。代价是可能漏掉深层缺口，但这是成功率和成本的权衡。

## W3 复盘自测（9 题）批改记录 2026-08-30

第一次自测：Q2/Q3/Q5/Q6 及格，Q4 半对，Q7 答偏，Q8 空白，Q9 方向对表述乱。
从"跟着敲都懂"到"能主动复述"差的就是练习，这轮批改后把错的都钉死：

### 必背的两道硬菜

**Q7 标准答案（防死循环/计划爆炸，面试必问）**：
1. replan_count < 3 熔断（路由层，第 4 次直接拒绝）
2. prompt 军规"任务总数不超过 8 个"（防膨胀）
3. 修改约束"只新增/改未完成任务"（防改写已完成成果）
再加一句：prompt 约束是第一道，代码卫生化兜底，熔断是最后的保险丝。

**Q8 标准答案（新任务没被执行，怎么排错）——按数据流向倒着查**：
1. 先查 replanner 的 return：键名拼对没（plan 不是 plam）；current_task 指没指向新任务
2. 再查路由：current_task >= len(plan) 是不是误判"到头了"，直接送去了 final
3. 再查状态卫生化：新任务是不是没被置成 pending
4. 最后才怀疑 executor 的索引
记忆：白板格子写对没 → 指针指向哪 → 路由怎么判 → executor 怎么取

### 纠正的事实错误（我之前记混了）

- evaluator **从不改 plan**，它只写 evaluation 判定书；标 failed 的是 executor
- replanner 的状态规则：completed 强制保留，其余（失败/新增/被改）**一律重置 pending**，
  新计划里没有任务以 failed 状态留下来
- Q4 混了数据流和控制流：判定书是数据（住白板上），路由读它选路（控制流），
  replanner 再从白板读 missing_info。数据不"通过 route 到达"任何地方，白板本身就是载体

### 补的细节

- route 返回的字符串是"钥匙"，要查映射表才知道目的地；三问的顺序也是设计（重规划优先于跑完了）
- 指针不重算的两种死法：重复执行已完成的任务 / 越界崩溃（plam 事故那种）
- Q9 整理成两句：每任务必查 = 缺口在还来得及补的时候被发现（后面还有位置插新任务）；
  一步一验 = 及时止损，不让后面的任务建立在坏数据上一直错到底

### 下一步

合卷把这 4 条复述一遍，全过才开 W4。

# W4 —— 鲁棒性周：从"正常能跑"到"出事也不怕"

## 本周加了什么（对着 W3 的增量）

四个机制，每个都对应一种"出事"：
- **Retry（base.py）**：工具调用失败且属瞬时故障（超时/429/5xx）→ 指数退避 1s/2s 重试 ≤2 次；
  404 这类永久故障不重试。
- **Checkpoint（graph.py + main.py）**：编译图时挂 SqliteSaver，每个节点跑完自动把白板
  快照存进 checkpoints.sqlite；进程死了用 --resume run_id 凭快照复活，从断掉的节点继续。
- **HITL（execute_python + human_gate）**：高危工具不让 executor 自动执行——登记
  pending_approval → 闸门节点 interrupt() 冻结全图 → CLI 问人 → Command(resume) 回注。
- **Memory（store.py）**：save_memory 写 SQLite（UNIQUE 去重），search_knowledge 用
  BM25+jieba 检索自己的 6 篇笔记。长期记忆让 Agent 从"每次归零的计算器"变成"越用越懂你"。

## 本周的坑（每个都是亲手踩的）

1. **悲观初值**：重试循环里 success 沿用了旧版初值 True，结果产出"带错误信息的成功回执"
   （success=True 但 error=404）。教训：循环重试必须默认悲观——没成功过就是没成功。
2. **checkpoint 序列化边界**：每两个节点之间有"序列化→存档→反序列化"，plan 和
   pending_approval 里的同名任务变成两份独立拷贝。在闸门里改 pending_approval 的状态，
   plan 里那份纹丝不动，最终任务清单显示已成功的任务是 pending。修法：按 id 找到
   plan 列表里那一份来改。教训：跨节点的对象引用不可信。
3. **孪生路由名**：route_after_eval / route_after_execute，给 executor 挂条件边时
   递错了函数——评估还没跑就去读 evaluation（None）直接崩。同族事故第三次
   （plam、task.id、pending_aproval 少个 p）。土办法：键名从 schemas.py 复制粘贴，不手打。
4. **人的否决是终审**：拒绝高危操作后，失败任务被重置 pending → 再审批 → 再拒绝……
   重规划连插三个新任务形成审批循环。修法：evaluator 加规则"失败原因是用户拒绝 →
   不再重试"。设计原则：否则 HITL 从保护机制退化成橡皮图章。
5. **中文检索的停用词**：搜"量子纠缠"返回了 3.0 的假相关——jieba 把查询切成词后，
   "的/完全/无关"这些词在笔记里到处都是，堆出了假分数。修法：停用词表 + 过滤单字，
   让"相关度"变诚实。BM25Okapi 对出现在半数以上文档的词会算出负 IDF，也是个冷知识。
6. 小怪合集：DTZ005（datetime.now() 不带时区，用 astimezone() 补）；
   PowerShell 的 \" 转义会切断 python -c 字符串（内部用单引号，嵌套用 chr() 拼）。

## 面试问答演练

问：断点恢复是怎么工作的？
答：compile 时挂 SqliteSaver，每个节点（super-step）跑完自动把完整白板 + 导航位置
按 thread_id 写进 SQLite。进程死了，用同一 thread_id 调 invoke(None)——None 的意思
是"不给新输入，看档案"——框架取最新快照、反序列化还原白板、从断掉的节点重入。
恢复粒度是节点级"至少一次"：死在节点中间的会重跑（我们真实遇到过：评估员死在
调 DeepSeek 半路，恢复后它重新评估了一次），已完成的节点绝不重跑。
快照我见过实物：checkpoints.sqlite 里躺着 11 次 run 共 137 份快照。

问：用户拒绝了高危操作，Agent 该怎么办？
答：把拒绝当终审。第一次实现时它会重置任务再问一次，形成审批循环——
后来在评估器里加了规则：失败原因是用户拒绝 → 不再重试。HITL 的目的是给人
控制权，反复骚扰人的审批是失败的设计。

问：为什么记忆用 SQLite 表 + BM25，不用向量库？
答：范围控制。BM25 零基础设施、结果可解释；已知代价是纯字面匹配——搜"断点续传"
搜不到讲 checkpoint 的笔记（语义相同字面不同），这正是向量检索要解决的问题，
留给项目二（RAG）正面回答。




# W5 —— 评测周：全项目含金量最高的一周

## 本周做了什么

- **数据集**：100 条（GitHub 分析 35 / 学习规划 34 / 问题解决 31；easy 25 / medium 47 / hard 28），
  其中 13 道必败/对抗题（不存在仓库、破解 WiFi、伪造诊断证明、预测股市……），
  专门测 Agent 会不会诚实拒绝。分三批生成，每批人工抽检。
- **Runner（run.py）**：并发 3 跑批、每条 trace 落盘 json（含步数/耗时/token/回执/任务终态）、
  --limit/--offset 断点续跑、无人值守时审批自动拒绝。
- **Token 记账（llm.py）**：BaseCallbackHandler 在每次 LLM 调用结束时累加 usage，
  runner 前后做差得到单条消耗（线程安全，有锁）。
- **Judge（judge.py）**：rubric 覆盖率判分法，逐要点输出 hit + evidence，覆盖率 ≥0.6 判成功。
- **盲测校准（calibrate.py）**：抽 20 份我人工判，和 judge 对账——一致率 85%，达标。
- **指标（evaluate.py）**：七个指标聚合，产出 docs/experiments.md 对比报告。
- 跑完 4 遍全量 = 400 份 trace + 400 份判定。实际花费约 ¥32（预算 ¥50 内）。

## 最重要的领悟：实验假设没有被证实，怎么办

我预设"Adaptive 重规划会明显提升成功率"。真实结果：**打平**。
总体成功率 Fixed 96% vs Adaptive 97%（+1pp，噪声范围内）；
逐题配对：Adaptive 独胜 3 题 vs Fixed 独胜 3 题；hard 题 23:24。

一开始有点沮丧，后来想明白了——这个结果比"大获全胜"值钱：
1. **收益的边界**：首拆计划成功率本来就 94%+，简单任务为主的目标分布上，
   重规划没有施展空间。它的收益集中在"首拆计划失效"场景
   （实测：文档搬家后自动改抓新地址，一次重规划就救回来了）；
2. **代价被定量了**：1.59 倍成本、48% 重规划触发率、+2 步、+10 秒。
   重规划是保险不是免费午餐，保费现在有数字了；
3. **Fixed 也不是白给**：它独胜的 3 题说明重规划自身会引入不稳定性
   （改计划改出新失败），熔断机制确实必要。

面试话术升级："我的实验没有证明 Adaptive 全面占优——它证明的是更细的东西：
收益取决于任务分布，代价可以精确量化。简单任务占比越高，重规划越亏。"

## 本周的坑

1. **sys.path 第三次**：直接跑 `python evals/run.py` 报 No module named 'app'——
   脚本模式只把脚本目录放进搜索路径。标准解法：`python -m evals.run`（-m 会把
   当前目录放进去）。这个知识点三周撞了三次，终于长在脑子里了。
2. **judge 返回 None**：with_structured_output 偶尔返回 None（模型回了普通文本
   没走工具调用）。防御：None 也算一次失败，进自愈重试循环。
   顺带学会了"防御要跟着节点走"——planner 有的自愈循环，每个调 LLM 的节点都该有。
3. **gitignore 粘连**：echo 追加时原文件末尾没换行，memory.sqlite 粘在上一行变成
   results/memory.sqlite，根本没生效。教训：改配置文件先看末尾有没有换行。
4. **校准表的锚定偏误（本周最有含金量的设计缺陷）**：第一版人工判卷表的表头
   直接显示 judge 判定——人打勾前看到了机器答案，100% 一致率全是水分。
   修法：盲测版隐藏 judge 判定 + 对照组混洗，重测得 85%。
   这段"发现自己校准设计有毛病→改盲测"的过程，比 85% 本身更值钱。
5. **judge 的盲区（LLM-as-judge 固有缺陷）**：judge 判的是"答卷是否命中要点"（形式），
   不校验事实真伪——一个自洽的幻觉答案能拿满分（实测：某 Rust 高星仓库榜单
   里混着可疑数据照样 1.0）。对策：人工校准重点复核事实榜单类题目。
6. 停用词假相关：BM25 对"的/完全/无关"这类词照算分数，"量子纠缠"查询能出 3.0
   假相关。修法：停用词表 + 过滤单字。检索系统的第一课是清洗不是算法。

## 面试问答演练

问：你怎么评估 LLM 应用的效果？
答：回归评测思路——固定 100 条评测集当考卷，每次改动重跑对比。
判分用 rubric 要点覆盖率（生成类任务没有唯一正确答案，精确匹配会把对的判错），
机器阅卷用 LLM-as-judge（温度 0），再抽 20 份盲测人工校准——一致率 85%。
主动交代局限：judge 不校验事实真伪、样本量小、结论只在自家对照内有效。

问：你的实验结论是什么？
答：（见上面"最重要的领悟"，三层：边界/代价/保险定位 + 数字）
