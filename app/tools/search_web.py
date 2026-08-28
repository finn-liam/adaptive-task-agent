"""search_web：全网搜索。Tavily 优先，无 Key 或失败时降级 DuckDuckGo（决策 D2）"""

import os

import httpx
from dotenv import load_dotenv

TAVILY_API = "https://api.tavily.com/search"


def _tavily(query: str) -> str:
    load_dotenv()
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        raise RuntimeError("未配置 TAVILY_API_KEY")
    resp = httpx.post(
        TAVILY_API,
        json={"api_key": key, "query": query, "max_results": 5},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Tavily 异常 {resp.status_code}: {resp.text[:200]}")
    results = resp.json().get("results", [])
    if not results:
        return "Tavily：没有搜到相关结果"
    lines = [
        f"{i}. {r['title']}\n   {r['url']}\n   {r['content'][:200]}"
        for i, r in enumerate(results, 1)
    ]
    return "Tavily 搜索结果：\n" + "\n".join(lines)


def _ddg(query: str) -> str:
    from ddgs import DDGS  # 延迟导入：只有降级那一刻才加载
    items = list(DDGS().text(query, max_results=5))
    if not items:
        return "DuckDuckGo：没有搜到相关结果"
    lines = [
        f"{i}. {r['title']}\n   {r['href']}\n   {r['body'][:200]}"
        for i, r in enumerate(items, 1)
    ]
    return "DuckDuckGo 搜索结果（降级模式）：\n" + "\n".join(lines)


def search_web(query: str) -> str:
    if not query:
        raise ValueError("search_web 需要 query 参数")
    try:
        return _tavily(query)
    except Exception as e:          # noqa: BLE001 —— 降级链需要兜住一切，属刻意设计（见决策 D2）
        # 降级 ≠ 吞错误：把降级原因随结果一起带走
        return _ddg(query) + f"\n\n[注：Tavily 不可用（{e}），本次结果来自降级通道]"