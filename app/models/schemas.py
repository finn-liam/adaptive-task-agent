from typing import Literal,get_args,Any
from pydantic import BaseModel

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
# 反推出纯字符串元组，后面的注册表和 Prompt 都会复用它
TOOL_NAMES = get_args(ToolName)

class Task(BaseModel):
    """Agent计划中的单个任务"""
    id: str                             #"t1","t2"...；重规划插入的新任务延续编号
    description: str                    #要干什么的自然语言描述
    tool: ToolName | None               #用哪个工具执行；V1约定不允许为None
    tool_args: dict[str, Any] |None = None          #调用工具的参数
    depends_on: list[str] = []                      #必须等这些任务完成了，本任务才开始
    status: Literal["pending","running","completed","failed"] = "pending"

class Observation(BaseModel):
    """一次工具执行的记录"""
    task_id: str                    #观察属于哪个任务
    tool: ToolName                  #实际用了哪个工具
    success: bool                   #是否执行成功
    summary: str                    #截断后给LLM看的内容
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
    reasoning: str
    tasks: list[Task]