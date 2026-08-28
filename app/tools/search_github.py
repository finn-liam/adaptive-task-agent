"""search_github：GitHub 官方接口——搜仓库 / 拉 README"""

import base64
import os

import httpx
from dotenv import load_dotenv

API = "https://api.github.com"

def _headers() -> dict:
    load_dotenv()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("缺少githubtoken，请确认填入.env")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

def _check(resp: httpx.Response) -> dict:
    """统一的响应安检：顺序有讲究——先特殊后一般"""
    remaining = resp.headers.get("x-ratelimit-remaining", "?")
    if resp.status_code in (403, 429):
        raise RuntimeError(f"GitHub 限流（剩余额度 {remaining}），稍后再试")
    if resp.status_code == 404:
        raise RuntimeError("目标不存在：私有仓库、拼写错误或根本没有")
    if resp.status_code != 200:
        raise RuntimeError(f"GitHub API 异常 {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def search_github(query: str = "", action: str = "search", repo: str = "") -> str:
    """action="search"：关键词搜仓库；action="readme"：repo="owner/name" 拉 README"""
    if action == "search":
        if not query:
            raise ValueError("search 模式需要 query 参数")
        data = _check(httpx.get(
            f"{API}/search/repositories",
            params={"q": query, "per_page": 5},
            headers=_headers(), timeout=30,
        ))
        items = data.get("items", [])
        if not items:
            return "没有搜到匹配的仓库"
        lines = [
            f"- {it['full_name']} ⭐{it['stargazers_count']}｜{(it.get('description') or '')[:100]}"
            for it in items
        ]
        return "GitHub 搜索结果：\n" + "\n".join(lines)

    if action == "readme":
        if not repo:
            raise ValueError("readme 模式需要 repo 参数（格式：owner/name）")
        data = _check(httpx.get(f"{API}/repos/{repo}/readme",
                                headers=_headers(), timeout=30))
        text = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return f"{repo} 的 README：\n{text}"

    raise ValueError(f"未知 action：{action}")