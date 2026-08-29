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

