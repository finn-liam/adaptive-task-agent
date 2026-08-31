"""工具注册表/工具电话簿：名字 → 实现函数。新工具出生后在这里挂载一行"""
from app.memory.store import save_memory, search_knowledge
from app.tools.execute_python import execute_python
from app.tools.fetch_url import fetch_url
from app.tools.read_file import read_file
from app.tools.search_github import search_github
from app.tools.search_web import search_web

TOOL_REGISTRY: dict = {
    "read_file":read_file,
    "fetch_url": fetch_url,
    "search_github": search_github,
    "search_web": search_web,
    "execute_python": execute_python,
    "save_memory": save_memory,
    "search_knowledge": search_knowledge,
    }

