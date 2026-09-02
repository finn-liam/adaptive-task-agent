"""FastAPI 服务：把 CLI 的 Agent 变成 HTTP 服务（W6-1）

架构（决策：砍 Redis，单进程内 queue 直连）：
- POST /api/runs        发起一次运行：后台线程用 graph.stream() 跑图，节点更新推进程内队列
- GET  /api/runs/{id}/events  SSE 实时事件流（队列 → 浏览器）
- GET  /api/runs/{id}   当前白板快照 + 状态
- POST /api/runs/{id}/approvals  HITL 审批回注（网页按钮 → 线程里的图继续跑）
"""

import asyncio
import json
import queue
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from langgraph.types import Command
from pydantic import BaseModel

from app.agent.graph import build_graph

app = FastAPI(title="Adaptive Task Planning Agent")
STATIC = Path(__file__).resolve().parent / "static"

RUNS = {}          # run_id → {queue, state, status, approval_event, approved}


class RunCreate(BaseModel):
    goal: str
    adaptive: bool = True


class Approval(BaseModel):
    approved: bool


def _emit(run_id: str, event: str, data):
    """线程安全地把一条事件推进该 run 的队列（SSE 端稍后取走）"""
    RUNS[run_id]["queue"].put({"event": event, "data": data})


def _execute(run_id: str, goal: str, adaptive: bool):
    """后台线程：stream 模式跑图，节点更新→事件队列；审批→暂停等人→回注"""
    payload = {"run_id": run_id, "user_goal": goal, "adaptive": adaptive,
               "plan": [], "current_task": 0, "retry_count": 0, "replan_count": 0,
               "observations": [], "evaluation": None, "pending_approval": None,
               "final_answer": "", "status": "planning"}
    config = {"configurable": {"thread_id": run_id}}
    next_input = payload

    try:
        for _ in range(3):                       # 审批最多 3 轮，防极端循环
            interrupted = False
            for chunk in build_graph().stream(next_input, config, stream_mode="updates"):
                if "__interrupt__" in chunk:     # 图请求人工审批
                    interrupted = True
                    task = RUNS[run_id]["state"].get("pending_approval")
                    _emit(run_id, "hitl_request", {
                        "task_id": getattr(task, "id", "?"),
                        "code": (getattr(task, "tool_args", {}) or {}).get("code", "")
                                if task else "",
                    })
                    ev = threading.Event()       # 等人点按钮（最多等 5 分钟）
                    RUNS[run_id]["approval_event"] = ev
                    ev.wait(timeout=300)
                    approved = RUNS[run_id].get("approved", False)
                    RUNS[run_id]["approved"] = None
                    _emit(run_id, "hitl_resolved", {"approved": approved})
                    break
                for node, update in chunk.items():
                    if isinstance(update, dict):
                        st = RUNS[run_id]["state"]
                        for k, v in update.items():
                            # observations 必须模拟 operator.add 追加语义，否则被覆盖
                            if k == "observations" and isinstance(v, list):
                                st.setdefault("observations", []).extend(v)
                            else:
                                st[k] = v
                    _emit(run_id, "node_update", {"node": node})

            if not interrupted:
                RUNS[run_id]["status"] = "done"
                _emit(run_id, "final", RUNS[run_id]["state"].get("final_answer", ""))
                return
            next_input = Command(resume={"approved": approved})

        RUNS[run_id]["status"] = "failed"
        _emit(run_id, "error", "审批循环超出上限")
    except Exception as e:                       # noqa: BLE001 —— 后台线程不能静默死掉
        RUNS[run_id]["status"] = "failed"
        _emit(run_id, "error", f"{type(e).__name__}: {e}")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/api/runs")
def create_run(body: RunCreate):
    if not body.goal.strip():
        raise HTTPException(status_code=400, detail="goal 不能为空")
    run_id = uuid.uuid4().hex[:8]
    RUNS[run_id] = {"queue": queue.Queue(), "state": {}, "status": "running"}
    threading.Thread(target=_execute, args=(run_id, body.goal, body.adaptive),
                     daemon=True).start()
    return {"run_id": run_id}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail="run 不存在")
    return {"status": RUNS[run_id]["status"], "state": RUNS[run_id]["state"]}


@app.post("/api/runs/{run_id}/approvals")
def approve(run_id: str, body: Approval):
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail="run 不存在")
    ev = RUNS[run_id].get("approval_event")
    if ev is None:
        raise HTTPException(status_code=400, detail="当前没有等待审批的操作")
    RUNS[run_id]["approved"] = body.approved
    ev.set()                                     # 唤醒后台线程里的图
    return {"ok": True}


@app.get("/api/runs/{run_id}/events")
async def events(run_id: str):
    """SSE：把线程队列里的事件实时推给浏览器"""
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail="run 不存在")
    q: queue.Queue = RUNS[run_id]["queue"]

    async def gen():
        while True:
            try:
                item = await asyncio.to_thread(q.get, timeout=15)   # 阻塞 get 放线程，不卡事件循环
                payload = json.dumps(item["data"], ensure_ascii=False)
                yield f"event: {item['event']}\ndata: {payload}\n\n"
                if item["event"] in ("final", "error"):
                    break
            except queue.Empty:
                yield ": keepalive\n\n"          # 心跳：防止代理/浏览器掐断空闲连接

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
