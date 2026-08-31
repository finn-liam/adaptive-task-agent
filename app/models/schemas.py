import operator
from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel
from typing_extensions import TypedDict

# 工具名白名单：整个项目允许存在的全部工具，一个都不能多
ToolName = Literal[
    "search_web",
    "fetch_url",
    "search_github",
    "read_file",
    "search_knowledge",
    "save_memory",
    "execute_python",
]
# 输出为：typing.Literal['search_web', 'fetch_url', 'search_github', 'read_file', 'search_knowledge', 'save_memory', 'execute_python']

# 反推出纯字符串元组，后面的注册表和 Prompt 都会复用它
TOOL_NAMES = get_args(ToolName)
# 输出为：('search_web', 'fetch_url', 'search_github', 'read_file', 'search_knowledge', 'save_memory', 'execute_python')

class Task(BaseModel):
    """Agent计划中的单个任务"""
    id: str                             #"t1","t2"...；重规划插入的新任务延续编号
    description: str                    #要干什么的自然语言描述
    tool: ToolName | None               #用哪个工具执行；V1约定不允许为None，防止llm幻觉名，用Literal锁
    tool_args: dict[str, Any] |None = None          #调用工具的参数
    depends_on: list[str] = []                      #必须等这些任务完成了，本任务才开始
    status: Literal["pending","running","completed","failed"] = "pending"   #待处理，运行中，已完成，失败

# tool_args 的示例输出：
# fetch_url 任务
# tool_args = {"url": "https://www.runoob.com/ai-agent/langgraph-quick-start.html"}
# # search_web 任务
# tool_args = {"query": "LangGraph Checkpoint 持久化机制"}
# # search_github 任务
# tool_args = {"action": "search", "query": "langgraph"}

class Observation(BaseModel):
    """一次工具执行的记录"""
    task_id: str                    #观察属于哪个任务
    tool: ToolName                  #实际用了哪个工具
    success: bool                   #是否执行成功
    summary: str                    #截断后给LLM看的内容。在base中。输出为： 头 1200 字符 + 省略标记 + 尾 400 字符：
    source_url: str | None = None   #信息来源链接,最终回答要附引用
    raw_ref: str | None = None      #原始全文落盘的路径
    error: str | None = None        #失败的原因
    latency_ms: int=0               #耗时毫秒数

class EvaluationResult(BaseModel):
    """评估器对单个任务结果的判定"""

    success: bool                       #任务意图有没有达成
    reason: str                          #判定依据，失败时要指出具体缺什么
    need_replan: bool                     #是否需要重规划
    missing_info: str | None = None     #缺口描述，重规划器的输入


class Plan(BaseModel):
    """一次规划产出的完整任务清单"""
    reasoning: str                      # 为什么这么规划，方便 debug 和演示
    tasks: list[Task]                   #任务数量约定 3~8 个，超界由调用方截断

class AgentState(TypedDict):
    """整张图共享的白板：所有节点的输入输出都长这样"""
    run_id: str                                   # 本次运行的身份证号，Checkpoint 用它找回现场
    user_goal: str                                # 用户原始目标，原样保存，后续节点随时回看
    adaptive: bool                                # True=自适应重规划；False=固定计划对照组（W5 用）
    plan: list[Task]                              # 当前任务清单，重规划时会被改写
    current_task: int                             # 下一个要执行的任务下标
    retry_count: int                              # 当前任务的重试次数
    replan_count: int                             # 已重规划次数
    observations: Annotated[list[Observation], operator.add]   # 节点各存各的，框架自动合并
    evaluation: EvaluationResult | None           # 最近一次评估结论
    pending_approval: Task | None                 # 等待人工审批的高危任务
    final_answer: str                             # 最终答案
    status: Literal[
        "planning", "executing", "evaluating", "waiting_human", "done", "failed"
    ]