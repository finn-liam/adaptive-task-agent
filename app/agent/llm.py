"""模型供应商单点封装 + 全局 token 记账"""
import os
import threading

from dotenv import load_dotenv
from langchain_core.callbacks import BaseCallbackHandler
from langchain_openai import ChatOpenAI

_lock = threading.Lock()
_usage = {"input": 0, "output": 0}          # 全项目累计（线程安全）


class UsageCollector(BaseCallbackHandler):
    """每次 LLM 调用结束时，把 usage 累加进全局计数"""

    def on_llm_end(self, response, **kwargs):
        usage = (getattr(response, "llm_output", None) or {}).get("token_usage") or {}
        with _lock:
            _usage["input"] += usage.get("prompt_tokens", 0) or 0
            _usage["output"] += usage.get("completion_tokens", 0) or 0


def usage_snapshot() -> dict:
    with _lock:
        return dict(_usage)                 # 返回副本，供 runner 前后做差


def make_llm() -> ChatOpenAI:
    load_dotenv()
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
        temperature=0,
        callbacks=[UsageCollector()],       # 记账器挂在这里，全项目所有调用自动入账
    )


