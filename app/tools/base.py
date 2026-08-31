"""run_tool：所有工具的公共包装器——治安、计时、截断、重试都在这里

W4-1 新增：指数退避重试。设计要点：
- 只重试"瞬时故障"（网络抖动/限流/5xx），永久故障（404/参数错）立即放弃；
- 等待时间翻倍（1s→2s），给对方喘息窗口，避免火上浇油；
- 重试外壳只在这一层，各工具内部完全不感知重试的存在。
"""

import time

from httpx import TimeoutException

from app.models.schemas import Observation
from app.tools.registry import TOOL_REGISTRY

# 值得重试的异常类型：超时（httpx）与连接失败（Python 内置）
RETRYABLE = (TimeoutException, ConnectionError)


def _is_retryable(error: Exception) -> bool:
    """瞬时故障才值得重试：网络抖动/限流/服务端崩；参数错、404 重试无意义"""
    if isinstance(error, RETRYABLE):
        return True

    # 工具抛的都是 RuntimeError("HTTP 404: ...") 这类字符串错误，
    # 所以从消息文本里认出限流（429）和服务端错误（5xx）
    msg = str(error)
    return "429" in msg or any(f"HTTP {c}" in msg for c in (500, 502, 503, 504))


def _truncate(text: str, head: int = 1200, tail: int = 400) -> str:
    """超长正文只留头尾，中间插省略标记（标记里的总长是 evaluator 判缺的依据）"""
    if len(text) <= head + tail:
        return text
    omitted = len(text) - head - tail
    return (
        text[:head]
        + f"\n\n……[中间省略{omitted}字符，全文共{len(text)}字符]……\n\n"
        + text[-tail:]
    )


def run_tool(name: str, args: dict) -> Observation:
    """按名字调用工具，无论发生什么都返回 Observation，绝不向调用方抛异常"""
    start = time.monotonic()                        # monotonic：专测耗时的时钟，不受系统改时间影响
    func = TOOL_REGISTRY.get(name)                  # 电话簿查号：.get 查无此人返回 None 而不是炸
    if func is None:
        # 工具不存在 = 一次失败的调用，与其他失败同待遇（契约：包装器外无异常）
        return Observation(
            task_id=args.get("task_id", ""),
            tool=name,
            success=False,
            summary="",
            error=f"未注册的工具:{name}",
            latency_ms=0,
        )

    # task_id 是"信封上的信息"：先取出来随回执走，不混进工具的原料里
    task_id = args.get("task_id", "")
    clean_args = {k: v for k, v in args.items() if k != "task_id"}

    result_text = ""
    error = None
    success = False                                 # 悲观初值：没有任何一次成功前，谈不上成功
    for attempt in range(3):                        # W4-1：首次 + 最多 2 次重试
        try:
            result_text = func(**clean_args)        # 开机投料：从电话簿取出的函数直接调用
            success = True                          # 眼见为实：成功那一刻才翻牌
            error = None
            break
        except Exception as e:  # noqa: BLE001 —— 边界哨兵：驯化一切异常 + 重试判断，刻意宽捕获
            error = f"{type(e).__name__}: {e}"      # 存字符串进回执（Observation.error 是 str）
            if attempt < 2 and _is_retryable(e):
                wait = 2 ** attempt                 # 指数退避：第1次失败等1s，第2次等2s
                print(f"    ⏳ 第{attempt + 1}次失败（{type(e).__name__}），{wait}s 后重试…")
                time.sleep(wait)
            else:
                break                               # 不可重试的错误，或重试用尽——放弃

    # 收口：两条路径汇合，只填一次回执（含重试总耗时，不只是最后一次的）
    return Observation(
        task_id=task_id,
        tool=name,
        success=success,
        summary=_truncate(result_text) if success else "",
        error=error,
        latency_ms=int((time.monotonic() - start) * 1000),
    )
