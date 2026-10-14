"""run_stream：把 invoke 的"一锤子执行"改成逐节点消费的循环

W7 新增：交互模式（排队消息 + 两段式 Ctrl-C）的执行底座。
- invoke 只在整图跑完或冻结时才交还控制权，中间无法插手；
- stream(stream_mode="updates") 每个节点跑完吐一个 chunk，这里是唯一能
  "看见节点边界"的位置——软停检查、排队消息投递点都挂在这条边界上。

返回的四种状态：
- completed        跑到 END；
- awaiting_approval 图冻结在 human_gate 的 interrupt() 上，载荷是 __interrupt__ chunk；
- paused_soft      stop_event 在节点边界被看到（两段式 Ctrl-C 的第一次）；
- paused_input     has_input() 报告排队消息到了（"不打断也能转向"的投递点）。

软停的安全性由既有 checkpointer 兜底：每个节点跑完都落了快照，
停在这里 = --resume 的同一套续跑机制，节点级"至少一次"语义不变。
"""

COMPLETED = "completed"
PAUSED_SOFT = "paused_soft"
PAUSED_INPUT = "paused_input"
AWAITING_APPROVAL = "awaiting_approval"


def run_stream(graph, payload, config, *, stop_event=None, has_input=None):
    """逐节点消费图，返回 (状态, interrupt 载荷)

    stop_event：threading.Event，由交互层在 Ctrl-C 时 set；worker 线程（本函数
    的调用方）只在节点边界看它一眼——正在跑的 LLM/HTTP 调用会自然跑完当前节点。
    has_input：返回 bool 的回调，队列非空时 True——投递不打断，只在边界注入。
    """
    for chunk in graph.stream(payload, config, stream_mode="updates"):
        # interrupt 检查必须排在软停之前：审批是终审，即使用户按了 Ctrl-C 也要先问
        if "__interrupt__" in chunk:
            return AWAITING_APPROVAL, chunk["__interrupt__"]
        if stop_event is not None and stop_event.is_set():
            return PAUSED_SOFT, None
        if has_input is not None and has_input():
            return PAUSED_INPUT, None
    return COMPLETED, None
