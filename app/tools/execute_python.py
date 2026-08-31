"""execute_python：受限计算器——AST 白名单防御，仅允许纯算术，高风险走 HITL"""
import ast
import operator as op

# ast 抽象语法树 
# operator 模块：把运算符变成普通函数。

_ALLOWED_OPS = {                                    # 运算符白名单
    ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul,
    ast.Div: op.truediv, ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod, ast.Pow: op.pow,
}

# 允许调用的函数名
_ALLOWED_FUNCS = {"abs":abs,"round":round,"min": min, "max": max, "len": len}


def _eval_node(node):
    """递归校验并计算：只认白名单内的语法节点，见到陌生脸直接报警"""
    # 数字常量（2、3.14）→ 直接放行，返回数值
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value                           # 数字常量 ✅
    # 二元运算（a + b、a * b）先查白名单type(node.op),拿到对应函数->递归的先算左边node.left，再算右边node.right，然后合并
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    # 一元正负号（-5 里的 -）
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        v = _eval_node(node.operand)
        return -v if isinstance(node.op, ast.USub) else +v
    # 函数调用，三重验身，禁止os.system(……)，函数名得是裸名字max(……)
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in _ALLOWED_FUNCS and not node.keywords):
        return _ALLOWED_FUNCS[node.func.id](*[_eval_node(a) for a in node.args])
    # 以上四类之外的一切：import、变量名、赋值、属性访问、字符串……全到这行来raise返回error
    raise ValueError(f"拒绝执行：包含白名单外的语法（{type(node).__name__}）")


def execute_python(code: str = "", expression: str = "") -> str:
    code = code or expression                       # LLM 可能猜两种参数名，都接
    if not code:
        raise ValueError("execute_python 需要 code 参数（一段纯算术表达式）")
    tree = ast.parse(code, mode="eval")             # 语法不符直接抛 SyntaxError
    result = _eval_node(tree.body)
    return f"计算结果：{result}"