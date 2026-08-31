"""execute_python：受限计算器——AST 白名单防御，仅允许纯算术，高风险走 HITL"""
import ast
import operator as op

_ALLOWED_OPS = {                                    # 运算符白名单
    ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul,
    ast.Div: op.truediv, ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod, ast.Pow: op.pow,
}

_ALLOWED_FUNCS = {"abs":abs,"round":round,"min": min, "max": max, "len": len}


def _eval_node(node):
    """递归校验并计算：只认白名单内的语法节点，见到陌生脸直接报警"""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value                           # 数字常量 ✅
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        v = _eval_node(node.operand)
        return -v if isinstance(node.op, ast.USub) else +v
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in _ALLOWED_FUNCS and not node.keywords):
        return _ALLOWED_FUNCS[node.func.id](*[_eval_node(a) for a in node.args])
    raise ValueError(f"拒绝执行：包含白名单外的语法（{type(node).__name__}）")


def execute_python(code: str = "", expression: str = "") -> str:
    code = code or expression                       # LLM 可能猜两种参数名，都接
    if not code:
        raise ValueError("execute_python 需要 code 参数（一段纯算术表达式）")
    tree = ast.parse(code, mode="eval")             # 语法不符直接抛 SyntaxError
    result = _eval_node(tree.body)
    return f"计算结果：{result}"