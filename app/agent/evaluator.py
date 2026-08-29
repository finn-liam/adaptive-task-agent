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
