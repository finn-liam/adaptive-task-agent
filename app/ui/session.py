"""W7 交互层：排队消息 + 两段式 Ctrl-C + 中断后可编辑重发

线程模型（与被删掉的 W6 Web 版事件驱动一脉相承，这次落在 CLI 上）：
- 主线程 = asyncio 事件循环，独占所有 prompt_async（目标 / 排队输入 / 审批 / 编辑重发）；
- 图 = asyncio.to_thread 里的 worker 线程，run_stream 逐节点消费；
- 软中断 = threading.Event 桥接两个世界：asyncio 侧按 Ctrl-C 竖旗，worker 只在
  节点边界看旗——正在跑的 LLM/HTTP 调用自然跑完当前节点（同步栈无法取消）；
- patch_stdout 把 sys.stdout 换成线程安全代理，worker 的进度打印不打碎输入行。

三个交互承诺：
1. 输入排队：agent 干活时打字不发出也不丢——进队列，下一个节点边界投递为
   user_update，由 replanner 并入计划（"不打断也能转向"）；
2. 两段式 Ctrl-C：第一次停在当前节点之后（checkpoint 已落盘，等价 --resume 断点），
   窗口内第二次整进程退出；
3. 可编辑重发：软停后排队消息预填进编辑框，改完回车经 Command(update=...) 注入白板。
"""

import asyncio
import os
import sys
import time
import uuid
from threading import Event

from langgraph.types import Command

from app.agent.graph import build_graph, make_initial_state
from app.agent.runner import (
    AWAITING_APPROVAL,
    COMPLETED,
    PAUSED_INPUT,
    PAUSED_SOFT,
    run_stream,
)

RESET_WINDOW = 2.0   # 两次 Ctrl-C 间隔超过该秒数，计数重新来（防误触双击）


class _ExitSession(Exception):
    """用户在提示符处按 Ctrl-D：干净退出会话（区别于 Ctrl-C×2 的硬退）"""


class InteractiveSession:
    """交互会话：一台车 + 一个常驻输入位，跨多轮 run 复用同一个 PromptSession"""

    def __init__(self, fixed: bool = False):
        # lazy import：一次性模式（main.py 带 goal）和 evals 不加载 prompt_toolkit
        from prompt_toolkit.shortcuts import PromptSession

        self.ps = PromptSession()
        self.fixed = fixed
        self.stop_event = Event()
        self.queued: list[str] = []
        self._last_ctrl_c = 0.0
        self.run_id = ""

    # ---------- Ctrl-C 两段式 ----------

    def handle_ctrl_c(self, running: bool) -> None:
        """统一的 Ctrl-C 分级：窗口内第二次=硬退；第一次=软停（running）或提示"""
        now = time.monotonic()
        if now - self._last_ctrl_c <= RESET_WINDOW:
            self._hard_exit()
        self._last_ctrl_c = now
        if running:
            self.stop_event.set()
            print(f"\n[Ctrl-C] 当前节点完成后暂停；再按一次立即退出"
                  f"（checkpoint 保底，可 --resume {self.run_id}）", flush=True)
        else:
            print("\n[Ctrl-C] 再按一次退出。", flush=True)

    def _hard_exit(self) -> None:
        # worker 线程里的同步图无法安全取消，第二次 Ctrl-C 只能整进程带走。
        # 此刻各 prompt 都已干净退出（第一次 Ctrl-C 已结束 prompt_async，
        # raw_mode 上下文随之恢复），无需再收拾终端状态。
        print(f"\n[Ctrl-C ×2] 立即退出。run_id：{self.run_id}，"
              f"可用 --resume {self.run_id} 复活", flush=True)
        sys.stdout.flush()
        os._exit(130)

    # ---------- 提示符公共外壳 ----------

    async def _prompt(self, message: str, default: str | None = None) -> str:
        """Ctrl-C 走两段式计数（图已停，只提示），Ctrl-D 干净退出"""
        while True:
            try:
                return await self.ps.prompt_async(message, default=default or "")
            except KeyboardInterrupt:
                self.handle_ctrl_c(running=False)
            except EOFError:
                raise _ExitSession() from None

    async def _collect_input(self) -> None:
        """RUNNING 期间的常驻输入位：收到的行进队列，不打断也不丢失"""
        while True:
            try:
                line = await self.ps.prompt_async("（输入将排队，Ctrl-C=暂停）> ")
            except KeyboardInterrupt:
                self.handle_ctrl_c(running=True)
                return               # 软停已请求：输入位收摊，等节点边界生效
            except EOFError:
                return               # Ctrl-D：结束排队输入，run 继续跑完
            line = line.strip()
            if line:
                self.queued.append(line)
                head = line[:50] + ("…" if len(line) > 50 else "")
                print(f"⏳ 已排队（{len(self.queued)}）：{head}")

    # ---------- 一轮执行 ----------

    async def _turn(self, graph, payload, config) -> str:
        """跑一轮：审批与排队投递在内循环处理，返回 COMPLETED 或 PAUSED_SOFT"""
        collect = asyncio.create_task(self._collect_input())
        try:
            while True:
                status, _interrupt = await asyncio.to_thread(
                    run_stream, graph, payload, config,
                    stop_event=self.stop_event,
                    has_input=lambda: bool(self.queued),
                )
                if status == AWAITING_APPROVAL:
                    state = graph.get_state(config).values
                    await self._cancel_quietly(collect)
                    approved = await self._approval_prompt(state["pending_approval"])
                    # 审批互动本身消费掉软停意图：愿意批，就是要让它继续跑
                    self.stop_event.clear()
                    collect = asyncio.create_task(self._collect_input())
                    payload = Command(resume={"approved": approved})
                elif status == PAUSED_INPUT:
                    msgs, self.queued = self.queued, []
                    head = msgs[0][:50] + ("…" if len(msgs[0]) > 50 else "")
                    print(f"↩ 投递排队消息（{len(msgs)} 条，首条：{head}），"
                          "重规划时并入计划")
                    payload = Command(update={"user_update": "\n".join(msgs)})
                elif status == PAUSED_SOFT:
                    self.stop_event.clear()   # 暂停已送达用户，降旗等待下一步
                    return PAUSED_SOFT
                else:
                    return COMPLETED
        finally:
            await self._cancel_quietly(collect)

    @staticmethod
    async def _cancel_quietly(task: asyncio.Task) -> None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _approval_prompt(self, task) -> bool:
        print("\n 高危操作等待审批")
        print(f"   任务：{task.description}")
        print(f"   代码：{(task.tool_args or {}).get('code', '(见任务描述)')}")
        ans = await self._prompt("允许执行？[y/n] > ")
        return ans.strip().lower() == "y"

    async def _edit_resend(self) -> str | None:
        """软停后的编辑重发：排队消息预填编辑框；返回 None = 原样继续"""
        if self.queued:
            prefill, self.queued = "\n".join(self.queued), []
            msg = (await self._prompt(
                "编辑后回车发送（清空再回车=丢弃并原样继续）> ",
                default=prefill)).strip()
            return msg or None
        msg = (await self._prompt(
            "已暂停。输入补充指示回车=注入重规划；直接回车=原样继续 > ")).strip()
        return msg or None

    # ---------- 状态展示 ----------

    def _print_progress(self, graph, config) -> None:
        v = graph.get_state(config).values
        plan = v.get("plan") or []
        done = sum(1 for t in plan if t.status == "completed")
        print(f"\n—— 已暂停（run_id：{self.run_id}）——")
        print(f"进度：{done}/{len(plan)} 个任务完成｜重规划 {v.get('replan_count', 0)} 次"
              f"｜白板状态：{v.get('status')}")

    def _print_result(self, state) -> None:
        print("\n任务清单")
        for t in state["plan"]:
            print(f"[{t.id}] {t.status} | {t.tool} | {t.description}")
        print(f"执行回执（共 {len(state['observations'])} 张）")
        for o in state["observations"]:
            mark = "√" if o.success else "X"
            print(f"  {mark} [{o.task_id}] {o.tool}：{o.error or o.summary[:80]}")
        print("\n========== 最终答案 ==========")
        print(state["final_answer"])
        print(f"\n(运行状态：{state['status']}｜run_id：{self.run_id})")

    # ---------- 会话主循环 ----------

    async def run(self) -> None:
        from prompt_toolkit.patch_stdout import patch_stdout

        with patch_stdout():
            print("Adaptive Task Planning Agent · 交互模式")
            print("· agent 干活时输入会排队，不打断、不丢失")
            print("· Ctrl-C 第一次=当前节点后暂停（可编辑重发排队消息），第二次=退出")
            print("· 退出后凭 run_id 断点复活：--resume <run_id>\n")
            while True:
                goal = (await self._prompt("目标（直接回车=退出）> ")).strip()
                if not goal:
                    return
                await self._run_goal(goal)

    async def _run_goal(self, goal: str) -> None:
        self.run_id = uuid.uuid4().hex[:8]
        print(f"\n（本次 run_id：{self.run_id}，中断后可用 --resume {self.run_id} 复活）\n")
        graph = build_graph()
        config = {"configurable": {"thread_id": self.run_id}}
        payload = make_initial_state(self.run_id, goal, adaptive=not self.fixed)

        status = await self._turn(graph, payload, config)
        while status == PAUSED_SOFT:
            self._print_progress(graph, config)
            msg = await self._edit_resend()
            payload = Command(update={"user_update": msg}) if msg else None
            status = await self._turn(graph, payload, config)

        self._print_result(graph.get_state(config).values)
        # run 已到 END：残留的排队消息转正为下一个目标（预填编辑，可改可弃）
        if self.queued:
            nxt = (await self._prompt(
                "run 已结束。编辑排队消息作为新目标（清空=丢弃）> ",
                default="\n".join(self.queued))).strip()
            self.queued = []
            if nxt:
                await self._run_goal(nxt)


def run_interactive(fixed: bool = False) -> None:
    """main.py 无参数时的入口：交互会话替身一次性发车"""
    try:
        session = InteractiveSession(fixed=fixed)
    except Exception as e:   # 边界哨兵：管道/重定向下初始化输入层必败，给出可行动提示
        print(f"交互会话需要真实终端（输入层初始化失败：{type(e).__name__}）。\n"
              "请在 cmd / PowerShell / Windows Terminal 里运行；"
              '或用一次性模式：uv run python main.py "目标"')
        raise SystemExit(2) from e
    try:
        asyncio.run(session.run())
    except KeyboardInterrupt:
        # 落在非 prompt 等待点上的 Ctrl-C（通常是软停后的第二按）：按两段式语义硬退
        session._hard_exit()
    except _ExitSession:
        print("\n再见。")
