"""交互层两段式 Ctrl-C 分级逻辑的纯逻辑测试（不开终端、不进 asyncio）。

InteractiveSession.__init__ 会创建 PromptSession（需要真控制台），测试用
__new__ 绕过构造，只装配分级逻辑依赖的几个字段——被测的是决策，不是终端。
"""

from threading import Event

from app.ui.session import RESET_WINDOW, InteractiveSession


def _bare_session():
    s = InteractiveSession.__new__(InteractiveSession)
    s.stop_event = Event()
    s.queued = []
    s._last_ctrl_c = 0.0
    s.run_id = "test0001"
    s._hard_calls = 0
    # 简化替身：只计数，不真退进程
    s._hard_exit = lambda: setattr(s, "_hard_calls", s._hard_calls + 1)
    return s


def test_first_ctrl_c_while_running_requests_soft_stop():
    s = _bare_session()
    s.handle_ctrl_c(running=True)
    assert s.stop_event.is_set()          # 软停旗已竖起，worker 将在节点边界看到
    assert s._hard_calls == 0             # 不退进程


def test_second_ctrl_c_within_window_hard_exits():
    s = _bare_session()
    s.handle_ctrl_c(running=True)         # 第一次：软停
    s.handle_ctrl_c(running=True)         # 紧接着第二次：硬退
    assert s._hard_calls == 1


def test_ctrl_c_at_frozen_prompt_never_sets_soft_stop():
    # 图已停（审批/编辑/目标提示符）：第一次只提示，不动软停旗——
    # 否则审批通过后续跑会被残留的旗立即再次暂停
    s = _bare_session()
    s.handle_ctrl_c(running=False)
    assert not s.stop_event.is_set()
    assert s._hard_calls == 0
    s.handle_ctrl_c(running=False)        # 窗口内第二次：硬退
    assert s._hard_calls == 1


def test_stale_press_beyond_window_starts_over():
    # 超过 RESET_WINDOW 的"第二次"按第一次对待（防误触双击把人直接踢出去）
    s = _bare_session()
    s.handle_ctrl_c(running=True)
    s._last_ctrl_c -= RESET_WINDOW + 1    # 把上次按铃时间拨回窗口之外
    s.handle_ctrl_c(running=True)
    assert s._hard_calls == 0
    assert s.stop_event.is_set()
