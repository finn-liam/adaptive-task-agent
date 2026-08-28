"""fetch_url 行为测试：用 respx 伪造网络响应"""

import httpx
import pytest
import respx

from app.tools.fetch_url import fetch_url

HTML_BODY = "<html><body><main>" + "真实的正文内容，用于验证抓取管线。" * 30 + "</main></body></html>"


def test_fetch_extracts_text():
    with respx.mock:
        respx.get("https://fake.example/").mock(
            return_value=httpx.Response(200, text=HTML_BODY,
                                        headers={"content-type": "text/html; charset=utf-8"})
        )
        text = fetch_url("https://fake.example/")
    assert "真实的正文内容" in text


def test_404_raises():
    with respx.mock:
        respx.get("https://fake.example/missing").mock(return_value=httpx.Response(404))
        with pytest.raises(RuntimeError, match="404"):   # match= 还要求报错信息里含这段字
            fetch_url("https://fake.example/missing")


def test_rejects_non_html():
    with respx.mock:
        respx.get("https://fake.example/file").mock(
            return_value=httpx.Response(200, content=b"%PDF-1.7",
                                        headers={"content-type": "application/pdf"})
        )
        with pytest.raises(RuntimeError, match="只支持网页"):
            fetch_url("https://fake.example/file")