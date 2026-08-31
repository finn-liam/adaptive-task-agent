"""retry 行为测试：只重试瞬时故障、最多 2 次、指数等待"""

from httpx import TimeoutException

from app.tools.base import _is_retryable, run_tool
from app.tools.registry import TOOL_REGISTRY


def test_retries_transient_failure():
    calls = {"n": 0}

    def flaky(task_id=""):              # 前两次超时，第三次成功
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutException("模拟网络抖动")
        return "终于成功"

    original = TOOL_REGISTRY["read_file"]       # 存真身
    TOOL_REGISTRY["read_file"] = flaky          # 假函数顶替 read_file 的岗位
    try:
        obs = run_tool("read_file", {"task_id": "t1"})   # 顶替谁，就喊谁的名字
        assert obs.success and obs.summary == "终于成功"
        assert calls["n"] == 3                  # 恰好调了 3 次（首次+2次重试）
    finally:
        TOOL_REGISTRY["read_file"] = original   # 恢复真身，不留垃圾


def test_no_retry_on_permanent_error():
    calls = {"n": 0}

    def always_404(task_id=""):
        calls["n"] += 1
        raise RuntimeError("HTTP 404: 页面不存在")

    original = TOOL_REGISTRY["read_file"]
    TOOL_REGISTRY["read_file"] = always_404
    try:
        obs = run_tool("read_file", {"task_id": "t2"})
        assert not obs.success
        assert calls["n"] == 1                  # 404 是永久故障，只调 1 次
    finally:
        TOOL_REGISTRY["read_file"] = original


def test_retryable_detector():
    assert _is_retryable(TimeoutException("x")) is True
    assert _is_retryable(RuntimeError("HTTP 429: 限流")) is True
    assert _is_retryable(RuntimeError("HTTP 503: 服务维护")) is True
    assert _is_retryable(RuntimeError("HTTP 404: 没有这页")) is False