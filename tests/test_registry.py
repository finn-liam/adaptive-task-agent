"""守卫测试：白名单（户口本）与注册表（电话簿）必须完全一致"""


def test_registry_matches_whitelist():
    from app.models.schemas import TOOL_NAMES
    from app.tools.registry import TOOL_REGISTRY

    assert set(TOOL_REGISTRY) <= set(TOOL_NAMES), (
        f"注册了但白名单不认识：{set(TOOL_REGISTRY) - set(TOOL_NAMES)}"
    )