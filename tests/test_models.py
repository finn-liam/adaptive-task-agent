"""schemas.py 数据模型的校验行为测试"""

import pytest
from pydantic import ValidationError

from app.models.schemas import Observation, Plan, Task


def make_task(**overrides):
    """合法 Task 的标准工厂；overrides 用于临时改字段"""
    payload = {
        "id": "t1",
        "description": "获取 README",
        "tool": "fetch_url",
        "tool_args": {"url": "https://github.com/langchain-ai/langgraph"},
    }
    payload.update(overrides)
    return Task(**payload)


def test_task_legal_construction():
    t = make_task()
    assert t.id == "t1"
    assert t.status == "pending"          # 没传 status，默认值自动生效


def test_task_rejects_unknown_tool():
    with pytest.raises(ValidationError):  # 这里抛错 = 测试通过；不抛反而算失败
        make_task(tool="bing_search")


def test_observation_defaults():
    o = Observation(task_id="t1", tool="fetch_url", success=True, summary="摘要")
    assert o.latency_ms == 0
    assert o.source_url is None


def test_plan_nested_validation():
    p = Plan(reasoning="两步走", tasks=[make_task()])
    assert len(p.tasks) == 1
    assert p.tasks[0].tool == "fetch_url"


def test_serialization_roundtrip():
    t = make_task()
    restored = Task.model_validate_json(t.model_dump_json())
    assert restored == t                  # 序列化再回来，信息零丢失