"""read_file：只许读项目目录内的文本文件"""
from pathlib import Path

ALLOWED_ROOT = Path(__file__).resolve().parents[2]
MAX_BYTES = 200*1024

def read_file(path: str) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = ALLOWED_ROOT/p
    p = p.resolve()

    if not p.is_relative_to(ALLOWED_ROOT):
        raise ValueError(f"路径越界: {path}")
    elif not p.is_file():
        raise FileNotFoundError(f"文件不存在：{p}")
    elif p.stat().st_size > MAX_BYTES:
        raise ValueError(f"文件超过 200KB 上限：共 {p.stat().st_size} 字节")
    return p.read_text(encoding="utf-8")