"""run_tool：所有工具的公共包装器——治安、计时、截断都在这里"""

import time

from app.models.schemas import Observation
from app.tools.registry import TOOL_REGISTRY


def _truncate(text: str,head: int=1200,tail: int = 400) -> str:
    if len(text) <= head+tail:
        return text
    omitted = len(text) - head - tail
    return (
        text[:head]
        +f"\n\n……[中间省略{omitted}字符，全文共{len(text)}字符]……\n\n"
        +text[-tail:]
    )

def run_tool(name: str,args: dict) -> Observation:
    """按名字调用工具，无论发生什么都返回 Observation，绝不向调用方抛异常"""
    start = time.monotonic()
    func = TOOL_REGISTRY.get(name)                  #返回一个值
    if func is None:
        return Observation(
            task_id=args.get("task_id",""),
            tool=name,
            success=False,
            summary="",
            error=f"未注册的工具:{name}",
            latency_ms=0,
        )
    
    task_id = args.get("task_id","")        #如果找到"task.id"建就返回他的值，没有则给""
    clean_args = {k: v for k,v in args.items() if k != "task_id"}   #找到建不是"task.id"的键值对
    result_text = ""
    error = None
    success = True
    try:
        result_text = func(**clean_args)       #**的作用:字典拆成名字=值,func是上面返回的值
    except Exception as e:          ## noqa: BLE001 —— 工具失败必须隔离成 Observation，不允许炸掉 Agent 主循环
        success = False
        error = f"{type(e).__name__}: {e}"

    return Observation(
        task_id=task_id,
        tool=name,
        success=success,
        summary=_truncate(result_text) if success else "",
        error=error,
        latency_ms=int((time.monotonic() - start) * 1000),
    )  
