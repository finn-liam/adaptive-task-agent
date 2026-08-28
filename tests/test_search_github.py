"""search_github 行为测试：伪造 GitHub API 的 JSON 响应"""

import base64

import httpx
import pytest
import respx

from app.tools.search_github import search_github


def test_search_formats_results():
    with respx.mock:
        respx.get("https://api.github.com/search/repositories").mock(
            return_value=httpx.Response(200, json={"items": [
                {"full_name": "a/b", "stargazers_count": 12, "description": "示例仓库"},
            ]})
        )
        out = search_github(query="随便", action="search")
    assert "a/b" in out
    assert "⭐12" in out


def test_readme_decodes_base64():
    encoded = base64.b64encode(b"# Hello README").decode()
    with respx.mock:
        respx.get("https://api.github.com/repos/a/b/readme").mock(
            return_value=httpx.Response(200, json={"content": encoded})
        )
        out = search_github(repo="a/b", action="readme")
    assert "# Hello README" in out


def test_rate_limit_message():
    with respx.mock:
        respx.get("https://api.github.com/search/repositories").mock(
            return_value=httpx.Response(403, headers={"x-ratelimit-remaining": "0"})
        )
        with pytest.raises(RuntimeError, match="限流"):
            search_github(query="x", action="search")