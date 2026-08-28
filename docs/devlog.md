#W1做了什么我之前不知道的：
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