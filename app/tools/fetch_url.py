"""fetch_url：抓取网页正文，剔除导航脚本等噪音"""

import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}
NOISE_TAGS = ("script", "style", "nav", "header", "footer", "aside", "noscript")


def fetch_url(url: str) -> str:
    resp = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
    ctype = resp.headers.get("content-type", "")
    if ctype.startswith("application/json"):
        return resp.text[:5000]      # JSON API 直接返回原文——LLM 调结构化接口是合理行为
    if not ctype.startswith(("text/html", "text/plain")):
        raise RuntimeError(f"只支持网页/纯文本，拒绝该类型：{ctype}")

    soup = BeautifulSoup(resp.text, "lxml")

    for tag in soup(NOISE_TAGS):      # soup(标签名元组) = 找出全部匹配的标签
        tag.decompose()               # 连根拔除（含其内部所有内容）

    main = soup.find("main") or soup.find("article") or soup.body or soup
    lines = (ln.strip() for ln in main.get_text("\n").splitlines())
    text = "\n".join(ln for ln in lines if ln)

    if len(text) < 50:
        raise RuntimeError(f"正文只有 {len(text)} 字符，疑似没抓到有效内容：{url}")
    return text