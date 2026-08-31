"""evaluator：任务执行后判断是否真正达成意图，产出结构化判定"""

from app.agent.llm import make_llm
from app.models.schemas import AgentState, EvaluationResult

EVAL_PROMPT = """你是严格的检察员，判断一次工具执行是否真正达成了任务意图。

用户总目标{goal}

该任务的意图：{description}
工具执行回执:
{observations}

判定规则：
1. success=内容真正满足了任务意图(不是"工具没报错"就算成功;导航菜单、报错页、空内容都不算)
2. 若不成功,且总目标仍然需要这类信息: need_replan=true,并用一句中文写清缺了什么(missing_info)
3. reason 用一句话说明判定依据
"""

def evaluator_node(state: AgentState) -> dict:
    last_obs = state["observations"][-1]
    task = next(t for t in state["plan"] if t.id == last_obs.task_id)

    receipt = last_obs.summary if last_obs.success else f"执行失败：{last_obs.error}"
    prompt = (EVAL_PROMPT
              .replace("{goal}",state["user_goal"])
              .replace("{description}",task.description)
              .replace("{observations}",receipt[:1600])
    )
    result: EvaluationResult = make_llm().with_structured_output(
        EvaluationResult,method="function_calling").invoke(prompt)
    mark = "√√√ 通过" if result.success else ("循环 建议重规划" if result.need_replan else "X 失败跳过")
    print(f"🔍 [{task.id}]{mark} | {result.reason}")
    return {"evaluation":result}


# result = EvaluationResult(
#     success=True,                          # 内容真满足了任务意图
#     reason='搜索结果第一条就是 langchain-ai/langgraph，仓库名与 URL 明确，满足意图',
#     need_replan=False,                     # 不需要改计划
#     missing_info=None,                     # 无缺口
# )
# 节点返回：{"evaluation": 上面的对象} → 白板 evaluation 格子被覆盖为这份

# result = EvaluationResult(
#     success=False,
#     reason='工具执行报错（TypeError: read_file() missing path），未获取到任何内容',
#     need_replan=True,                      # 且总目标仍需要这个信息
#     missing_info='LangGraph Checkpoint 持久化的正文内容',
# )
# # missing_info 的去向：下一站 replanner 用 .replace("{missing}", ev.missing_info) 拼进 prompt