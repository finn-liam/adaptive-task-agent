"""工具电话簿：名字 → 实现函数。新工具出生后在这里挂载一行"""
from app.tools.read_file import read_file

TOOL_REGISTRY: dict = {
    "read_file":read_file,
    }

