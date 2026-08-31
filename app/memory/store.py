"""memory：Agent 的长期记忆——save_memory 写入经验，search_knowledge 检索本地笔记"""

import sqlite3
from datetime import datetime
from pathlib import Path

import jieba
from rank_bm25 import BM25Okapi

DB_PATH = "memory.sqlite"
KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "data" / "knowledge"

def _conn():
    """打开连接并确保表存在；content 加 UNIQUE 约束，重复内容数据库层直接拒绝"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT UNIQUE,
        created_at TEXT)
""")
    return conn

def save_memory(content: str) -> str:
    """把一条事实/经验写进长期记忆；重试安全靠 UNIQUE 去重兜底"""
    content = content.strip()
    if not content:
        raise ValueError("save_memory 需要 content 参数")
    conn = _conn()
    try:
        conn.execute("INSERT INTO memories (content, created_at) VALUES (?,?)",
                    (content, datetime.now().astimezone().isoformat(timespec="seconds")))
        conn.commit()
        return f"已记住：{content}"
    except sqlite3.IntegrityError:
        return f"这条已经在记忆里了: {content}"
    finally:
        conn.close()


_STOPWORDS = {"的", "了", "是", "在", "和", "与", "或", "一个", "这个", "使用",
              "可以", "通过", "就是", "以及", "但是", "如果"}


def _tokenize(text: str) -> list:
    """切词 + 去停用词 + 去单字——检索只看内容词"""
    return [w for w in jieba.cut_for_search(text)
            if w not in _STOPWORDS and len(w.strip()) > 1]
# —— search_knowledge：BM25 检索自己的笔记库 ——
_bm25_cache = None    # 索引缓存：语料运行期不变，建一次反复用

def _build_index():
    """扫描语料目录 → jieba 切词 → 建 BM25 索引"""
    docs = [(md.name,md.read_text(encoding="utf-8"))
            for md in sorted(KNOWLEDGE_DIR.glob("*.md"))]
    if not docs:
         raise RuntimeError(f"语料目录为空：{KNOWLEDGE_DIR}")
    corpus = [_tokenize(text) for _, text in docs]
    return docs,BM25Okapi(corpus)

def search_knowledge(query: str) -> str:
    """在笔记库里做 BM25 检索，返回最相关的两篇中的最佳段落"""
    global _bm25_cache
    if not query:
        raise ValueError("search_knowledge 需要 query 参数")
    if _bm25_cache == None:
        _bm25_cache = _build_index()
    docs,bm25 = _bm25_cache

    query_words = _tokenize(query)
    scores = bm25.get_scores(query_words)               # 每篇文档一个相关度分数
    ranked = sorted(zip(docs, scores), key=lambda p: p[1], reverse=True)[:2]

    lines = []
    for (name, text), score in ranked:
        if score <= 0:
            continue                                    # 完全不相关的跳过
        # 在这篇文档里找"查询词出现最多"的段落，只返回它（整篇太长，塞不下上下文）
        best = max(text.split("\n\n"),
                   key=lambda para: sum(w in para for w in query_words))
        lines.append(f"【{name}｜相关度 {score:.1f}】\n{best.strip()[:500]}")
    if not lines:
        return "笔记库里没有找到相关内容"
    return "笔记检索结果：\n" + "\n\n".join(lines)