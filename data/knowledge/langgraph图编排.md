# LangGraph 图编排核心概念

LangGraph 的世界观三句话：State（状态）是所有节点共用的白板，本 体只是普通字典；
每个节点就是一个普通函数，收到白板、干活、只返回"改了哪几格"的增量小 dict；
边决定节点顺序。AgentState 是 TypedDict 类型的白板图纸，运行时不存在它的实例。

节点返回字典的键 = 白板的格子名，这是和框架的合同：拼错不报错、只是静默不生效，
比崩溃更难查（真实事故：返回键写成 plam 导致 IndexError）。

observations 字段用 Annotated[list[Observation], operator.add] 声明：
多个节点各自追加回执，框架负责累加合并而不是覆盖。没有 reducer 的字段是"最后写入者赢"。

条件边 add_conditional_edges：路由函数检查白板，返回一个"钥匙"字符串，
映射表把钥匙翻译成下一个节点。图的代码书写顺序和执行顺序无关——
登记的是去哪的规则，路径是每次运行现场走出来的。
一个节点的出口只能归一种边管：固定边负责必然，条件边负责选择，并存会并行触发事故。

Checkpointer 断点恢复：编译图时挂 SqliteSaver，thread_id 关联快照；
每个节点（super-step）跑完自动把完整白板快照存进 SQLite。进程崩溃后用同一
thread_id 调 invoke(None, config) 就从最近快照继续。恢复粒度是节点级，
"至少一次"语义：死在节点中间的，恢复后该节点从头重跑。
checkpoint 每步之间有序列化边界，跨节点的对象引用不可信——
plan 和 pending_approval 里的同名任务会变成两份独立拷贝。

interrupt() 是图的暂停键：高危节点内调用后整张图冻结（快照已存档），
人工答复用 Command(resume=答复) 回注，节点从暂停点苏醒拿到答复继续。
interrupt 依赖 checkpointer——没有持久化，任何可暂停的智能体都不成立。
