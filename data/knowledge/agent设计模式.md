# Agent 设计模式：规划、评估与重规划

Plan-and-Execute 架构：planner 把模糊目标拆成结构化任务清单（结构化输出 +
Pydantic 校验，失败自动重试），executor 按指针逐个执行任务，每个任务干完必过
evaluator 质检。和 ReAct 的区别：控制流在代码和计划数据里，模型只在节点内出结论。

Fixed Planning vs Adaptive Planning 的对照实验：两种模式用同一条流水线、
同一个 planner，唯一区别是路由器里的 adaptive 开关——失败且需要补救时，
自适应模式进 replanner 改计划，固定模式装聋跳过。对照实验发现：
Fixed 模式所有任务都"成功"了但整体任务失败——计划完成率和任务真正成功是两回事，
评测要分开统计。

Re-planner 的三条纪律：已完成任务强制保留（代码层用状态存档逐个核对，
不信 LLM 的记性）；失败任务重置 pending 重新排队；replan_count 熔断上限 3 次，
超过就降级作答并诚实说明缺口。防止重规划死循环的三层防线：
熔断、prompt 军规限制任务总数、只允许新增或修改未完成任务。

Evaluator 的判定标准：不是"工具没报错"就叫成功——导航菜单、报错页、
被截断的内容都不算成功。评估输出是结构化的 EvaluationResult：
success、reason、need_replan、missing_info（缺口描述，重规划器的接力棒）。
LLM 的判定尺度会在多次运行间漂移，需要温度 0 + 结构化判据 + 人工校准收敛。

工具参数速查表要写进 prompt：LLM 不知道每个工具的参数名（比如给
search_github 填 keyword 而不是 query），也不知道 execute_python 只接受
单个纯算术表达式（写了赋值和 print 就会 SyntaxError）。教一次省十次失败。

人的否决是终审：HITL（human-in-the-loop）场景下用户拒绝了高危操作，
评估器必须判定不再重试——否则 Agent 会反复拿同一个危险操作骚扰人，
审批机制就从保护退化成橡皮图章。
