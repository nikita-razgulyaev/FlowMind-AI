"""Безопасный вычислитель выражений для Condition-ноды (вместо eval)."""
import ast
import operator

_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv}
_CMP = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le,
        ast.Gt: operator.gt, ast.GtE: operator.ge,
        ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b,
        ast.Is: operator.is_, ast.IsNot: operator.is_not}
_FUNCS = {"len": len, "str": str, "int": int, "float": float, "bool": bool,
          "abs": abs, "min": min, "max": max, "round": round}
_STR_METHODS = {"lower", "upper", "strip", "startswith", "endswith", "isdigit"}
MAX_LEN = 500


class UnsafeExpression(ValueError):
    pass


def safe_eval(expression: str, names: dict):
    if len(expression) > MAX_LEN:
        raise UnsafeExpression("Слишком длинное выражение")
    tree = ast.parse(expression.strip(), mode="eval")
    return _eval(tree.body, names)


def _eval(node, names):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in ("True", "False", "None"):
            return {"True": True, "False": False, "None": None}[node.id]
        if node.id in names:
            return names[node.id]
        raise UnsafeExpression(f"Неизвестная переменная: {node.id}")
    if isinstance(node, ast.BoolOp):
        values = [_eval(v, names) for v in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand, names)
        if isinstance(node.op, ast.Not):
            return not v
        if isinstance(node.op, ast.USub):
            return -v
        if isinstance(node.op, ast.UAdd):
            return +v
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        return _BIN[type(node.op)](_eval(node.left, names), _eval(node.right, names))
    if isinstance(node, ast.Compare):
        left = _eval(node.left, names)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval(comp, names)
            if type(op) not in _CMP or not _CMP[type(op)](left, right):
                if type(op) not in _CMP:
                    raise UnsafeExpression("Недопустимая операция сравнения")
                return False
            left = right
        return True
    if isinstance(node, ast.Subscript):
        container = _eval(node.value, names)
        key = _eval(node.slice, names)
        return container[key]
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_eval(e, names) for e in node.elts]
    if isinstance(node, ast.Call):
        args = [_eval(a, names) for a in node.args]
        if isinstance(node.func, ast.Name) and node.func.id in _FUNCS and not node.keywords:
            return _FUNCS[node.func.id](*args)
        if isinstance(node.func, ast.Attribute) and node.func.attr in _STR_METHODS:
            target = _eval(node.func.value, names)
            if isinstance(target, str) and not node.keywords:
                return getattr(target, node.func.attr)(*args)
    raise UnsafeExpression("Недопустимая конструкция в выражении")
