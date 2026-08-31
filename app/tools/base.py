"""run_tool：所有工具的公共包装器——治安、计时、截断都在这里"""

import time

from httpx import TimeoutException

from app.models.schemas import Observation
from app.tools.registry import TOOL_REGISTRY

RETRYABLE = (TimeoutException, ConnectionError) 

def _is_retryable(error: Exception) -> bool:
    """瞬时故障才值得重试：网络抖动/限流/服务端崩；参数错、404 重试无意义"""
    if isinstance(error, RETRYABLE):
        return True
    
    msg = str(error)
    return "429" in msg or any(f"HTTP {c}" in msg for c in (500, 502, 503, 504))
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
    success = False
    for attempt in range(3):                    # 首次 + 最多 2 次重试
        try:
            result_text = func(**clean_args)
            success = True
            error = None
            break
        except Exception as e:  # noqa: BLE001 —— 边界哨兵：驯化一切异常 + 重试判断，刻意宽捕获
            error = f"{type(e).__name__}: {e}" 
            if attempt < 2 and _is_retryable(e):
                wait = 2 ** attempt             # 1s → 2s（第三次失败就不再等）
                print(f"    ⏳ 第{attempt + 1}次失败（{type(e).__name__}），{wait}s 后重试…")
                time.sleep(wait)
            else:
                break                           # 不可重试，或重试用尽


    return Observation(
        task_id=task_id,
        tool=name,
        success=success,
        summary=_truncate(result_text) if success else "",
        error=error,
        latency_ms=int((time.monotonic() - start) * 1000),
    )  
