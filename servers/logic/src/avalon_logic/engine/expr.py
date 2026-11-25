"""表达式白名单编译器（设计文档 7.2 节）。

公式、效果条件、动作数值都是表达式，例如::

    1 - def / (def + 30 + 2 * level)
    (0.01 * self.atk + 0.02 * self.agi) * foe.stacks.碎晶
    hit.damage * pct // 100
    1 if n < 10 else 0.5 + 0.45 * exp(-0.15 * (n - 10))

安全做法：
- 用 Python 自带的 ``ast`` 只做**语法解析**，然后逐个节点检查是否在白名单里；
- 检查通过后把语法树转换成一组普通的 Python 函数（闭包）来求值，**从不调用 eval / exec / compile**；
- 只能调用白名单里的函数，不能访问下划线开头的属性，不能导入、赋值、循环、下标、关键字参数；
- 限制长度、节点数、嵌套深度和乘方大小，防止恶意或失误写出的表达式卡死后端。

取值规则：
- 变量只能从调用时传入的 ``env`` 里取；``a.b.c`` 逐级在字典里查找；
- :class:`ZeroDict` 里查不到的键返回 0（层数没叠时就是 0 层）。
"""

from __future__ import annotations

import ast
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

MAX_LENGTH = 500
MAX_NODES = 200
MAX_DEPTH = 30
MAX_POW_EXPONENT = 1000
MAX_MAGNITUDE = 1e18

Number = int | float | bool
Env = Mapping[str, Any]


class ExprError(ValueError):
    """表达式写法不正确（提交规则时就会发现）。"""


class ExprRuntimeError(ArithmeticError):
    """表达式在求值时出错（除以 0、变量不存在、数值过大……）。"""


class ZeroDict(dict):
    """查不到的键返回 0，用于层数、标记等"没有就是 0"的数据。"""

    def __missing__(self, key: str) -> int:
        return 0


def _round_half_up(value: float, digits: int = 0) -> float:
    """四舍五入（不是 Python 默认的"银行家舍入"），与旧版代码一致。"""
    scale = 10 ** int(digits)
    result = math.floor(value * scale + 0.5) / scale
    return int(result) if digits == 0 else result


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _checked_exp(value: float) -> float:
    if value > 700:
        raise ExprRuntimeError("exp 的参数过大")
    return math.exp(value)


def _checked_sqrt(value: float) -> float:
    if value < 0:
        raise ExprRuntimeError("sqrt 不能对负数开方")
    return math.sqrt(value)


FUNCTIONS: dict[str, tuple[Callable[..., Number], int, int]] = {
    # 名称: (函数, 最少参数个数, 最多参数个数)
    "min": (min, 2, 8),
    "max": (max, 2, 8),
    "abs": (abs, 1, 1),
    "floor": (math.floor, 1, 1),
    "ceil": (math.ceil, 1, 1),
    "round": (_round_half_up, 1, 2),
    "sqrt": (_checked_sqrt, 1, 1),
    "exp": (_checked_exp, 1, 1),
    "clamp": (_clamp, 3, 3),
}

_BIN_OPS: dict[type[ast.operator], str] = {
    ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
    ast.FloorDiv: "//", ast.Mod: "%", ast.Pow: "**",
}
_CMP_OPS: dict[type[ast.cmpop], Callable[[Any, Any], bool]] = {
    ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b,
}

Evaluator = Callable[[Env], Any]


@dataclass(frozen=True)
class CompiledExpr:
    source: str
    run: Evaluator = field(repr=False, compare=False)
    # 用到的根变量名（self、foe、hit、round……）
    names: frozenset[str] = frozenset()
    # 用到的完整路径，如 ("self", "atk")、("foe", "stacks", "碎晶")，供规则校验检查引用是否存在
    paths: frozenset[tuple[str, ...]] = frozenset()
    # 调用的公式名（检查公式之间有没有循环调用）
    calls: frozenset[str] = frozenset()

    def __call__(self, env: Env) -> Any:
        return self.run(env)

    def number(self, env: Env) -> float:
        value = self.run(env)
        if isinstance(value, bool):
            return int(value)
        if not isinstance(value, (int, float)):
            raise ExprRuntimeError("表达式结果不是数字")
        return value


def _check_magnitude(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        raise ExprRuntimeError("计算结果不是有效数字")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and abs(value) > MAX_MAGNITUDE:
        raise ExprRuntimeError("计算结果过大")
    return value


def _arith(op: str, a: Any, b: Any) -> Any:
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise ExprRuntimeError(f"运算 {op} 的两边必须是数字")
    try:
        if op == "+":
            r = a + b
        elif op == "-":
            r = a - b
        elif op == "*":
            r = a * b
        elif op == "/":
            r = a / b
        elif op == "//":
            r = a // b
        elif op == "%":
            r = a % b
        else:
            if abs(b) > MAX_POW_EXPONENT:
                raise ExprRuntimeError("乘方的指数过大")
            r = a ** b
            if isinstance(r, complex):
                raise ExprRuntimeError("乘方结果不是实数")
    except ZeroDivisionError as exc:
        raise ExprRuntimeError("除数不能为 0") from exc
    except OverflowError as exc:
        raise ExprRuntimeError("计算结果过大") from exc
    return _check_magnitude(r)


def _lookup(env: Env, path: tuple[str, ...]) -> Any:
    current: Any = env
    for index, part in enumerate(path):
        if isinstance(current, Mapping):
            if part in current or isinstance(current, ZeroDict):
                current = current[part]
                continue
        raise ExprRuntimeError(f"变量不存在：{'.'.join(path[: index + 1])}")
    if isinstance(current, Mapping):
        raise ExprRuntimeError(f"变量 {'.'.join(path)} 不是数值，还需要写到下一级")
    return current


# 运行时放公式的位置：env[FORMULAS_KEY][公式名](**参数) → 数值。下划线开头，表达式里写不到它
FORMULAS_KEY = "_formulas"


class _Compiler:
    def __init__(self, allowed_names: frozenset[str] | None,
                 formulas: Mapping[str, tuple[str, ...]] | None = None) -> None:
        self.allowed_names = allowed_names
        self.formulas = formulas or {}
        self.names: set[str] = set()
        self.paths: set[tuple[str, ...]] = set()
        self.calls: set[str] = set()
        self.nodes = 0

    def fail(self, node: ast.AST, message: str) -> ExprError:
        col = getattr(node, "col_offset", None)
        where = f"（第 {col + 1} 个字符附近）" if col is not None else ""
        return ExprError(message + where)

    def build(self, node: ast.AST, depth: int = 0) -> Evaluator:
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise ExprError(f"表达式过长：最多 {MAX_NODES} 个部分")
        if depth > MAX_DEPTH:
            raise ExprError(f"表达式嵌套过深：最多 {MAX_DEPTH} 层")
        d = depth + 1

        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, bool) or isinstance(value, (int, float)):
                return lambda env, v=value: v
            raise self.fail(node, "只能写数字，不能写文字")

        if isinstance(node, (ast.Name, ast.Attribute)):
            path = self._path(node)
            root = path[0]
            if root in FUNCTIONS:
                raise self.fail(node, f"{root} 是函数，要写成 {root}(...)")
            if self.allowed_names is not None and root not in self.allowed_names:
                allowed = "、".join(sorted(self.allowed_names)) or "（无）"
                raise self.fail(node, f"不认识的变量 {root}，这里能用的变量有：{allowed}")
            self.names.add(root)
            self.paths.add(path)
            return lambda env, p=path: _lookup(env, p)

        if isinstance(node, ast.BinOp):
            op = _BIN_OPS.get(type(node.op))
            if op is None:
                raise self.fail(node, "不支持这个运算符")
            left, right = self.build(node.left, d), self.build(node.right, d)
            return lambda env: _arith(op, left(env), right(env))

        if isinstance(node, ast.UnaryOp):
            operand = self.build(node.operand, d)
            if isinstance(node.op, ast.USub):
                return lambda env: _arith("-", 0, operand(env))
            if isinstance(node.op, ast.UAdd):
                return lambda env: _arith("+", 0, operand(env))
            if isinstance(node.op, ast.Not):
                return lambda env: not operand(env)
            raise self.fail(node, "不支持这个运算符")

        if isinstance(node, ast.BoolOp):
            parts = [self.build(v, d) for v in node.values]
            if isinstance(node.op, ast.And):
                return lambda env: all(p(env) for p in parts)
            return lambda env: any(p(env) for p in parts)

        if isinstance(node, ast.Compare):
            first = self.build(node.left, d)
            ops = []
            for op_node, comparator in zip(node.ops, node.comparators):
                fn = _CMP_OPS.get(type(op_node))
                if fn is None:
                    raise self.fail(node, "只能用 > >= < <= == != 比较")
                ops.append((fn, self.build(comparator, d)))

            def compare(env: Env) -> bool:
                left = first(env)
                for fn, right_eval in ops:
                    right = right_eval(env)
                    if not fn(left, right):
                        return False
                    left = right
                return True

            return compare

        if isinstance(node, ast.IfExp):
            test, body, orelse = self.build(node.test, d), self.build(node.body, d), self.build(node.orelse, d)
            return lambda env: body(env) if test(env) else orelse(env)

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in self.formulas:
            return self._formula_call(node, d)

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
                allowed = "、".join(FUNCTIONS)
                extra = "，或者已有的公式" if self.formulas else ""
                raise self.fail(node, f"只能调用这些函数：{allowed}{extra}")
            if node.keywords:
                raise self.fail(node, "函数参数不能写成 名字=值 的形式")
            name = node.func.id
            fn, low, high = FUNCTIONS[name]
            if not low <= len(node.args) <= high:
                count = str(low) if low == high else f"{low}~{high}"
                raise self.fail(node, f"{name} 需要 {count} 个参数")
            if any(isinstance(a, ast.Starred) for a in node.args):
                raise self.fail(node, "函数参数不支持 * 展开")
            args = [self.build(a, d) for a in node.args]

            def call(env: Env) -> Any:
                values = [a(env) for a in args]
                try:
                    return _check_magnitude(fn(*values))
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ExprRuntimeError(f"{name} 计算出错") from exc

            return call

        raise self.fail(node, f"不支持这种写法：{type(node).__name__}")

    def _formula_call(self, node: ast.Call, d: int) -> Evaluator:
        """调用公式：公式名(值, 值…) 按公式的变量顺序，或者 公式名(变量=值, …)。每个变量都要给值。"""
        name = node.func.id  # type: ignore[union-attr]
        params = self.formulas[name]
        if any(isinstance(a, ast.Starred) for a in node.args) or any(k.arg is None for k in node.keywords):
            raise self.fail(node, "公式的参数不支持 * 展开")
        if len(node.args) > len(params):
            raise self.fail(node, f"公式 {name} 只有 {len(params)} 个变量：{'、'.join(params) or '无'}")
        given: dict[str, Evaluator] = {}
        for param, arg in zip(params, node.args, strict=False):    # 上面已检查参数不多于变量
            given[param] = self.build(arg, d)
        for keyword in node.keywords:
            if keyword.arg not in params:
                raise self.fail(node, f"公式 {name} 没有变量 {keyword.arg}（有：{'、'.join(params) or '无'}）")
            if keyword.arg in given:
                raise self.fail(node, f"公式 {name} 的变量 {keyword.arg} 给了两次")
            given[keyword.arg] = self.build(keyword.value, d)
        missing = [p for p in params if p not in given]
        if missing:
            raise self.fail(node, f"调用公式 {name} 还要给这些变量的值：{'、'.join(missing)}")
        self.calls.add(name)

        def call(env: Env) -> Any:
            table = env.get(FORMULAS_KEY) if isinstance(env, Mapping) else None
            if not table or name not in table:
                raise ExprRuntimeError(f"公式 {name} 不存在")
            return _check_magnitude(table[name](**{k: v(env) for k, v in given.items()}))

        return call

    def _path(self, node: ast.AST) -> tuple[str, ...]:
        parts: list[str] = []
        current = node
        while isinstance(current, ast.Attribute):
            if current.attr.startswith("_"):
                raise self.fail(current, "不能使用下划线开头的名称")
            parts.append(current.attr)
            current = current.value
        if not isinstance(current, ast.Name):
            raise self.fail(node, "变量只能写成 名称.名称 的形式")
        if current.id.startswith("_"):
            raise self.fail(current, "不能使用下划线开头的名称")
        parts.append(current.id)
        return tuple(reversed(parts))


def compile_expr(source: str, allowed_names: set[str] | frozenset[str] | None = None,
                 formulas: Mapping[str, tuple[str, ...]] | None = None) -> CompiledExpr:
    """检查并编译表达式。allowed_names 限定能用的根变量名；不传则不限制。
    formulas：能调用的公式（公式名 → 变量名），不传就不能调用公式。

    写法不正确时抛出 :class:`ExprError`，错误信息是中文。
    """
    if not isinstance(source, str) or not source.strip():
        raise ExprError("表达式不能为空")
    text = source.strip()
    if len(text) > MAX_LENGTH:
        raise ExprError(f"表达式过长：最多 {MAX_LENGTH} 个字符")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        where = f"（第 {exc.offset} 个字符附近）" if exc.offset else ""
        raise ExprError("表达式语法错误" + where) from exc
    compiler = _Compiler(frozenset(allowed_names) if allowed_names is not None else None, formulas)
    run = compiler.build(tree.body)
    return CompiledExpr(
        source=text,
        run=run,
        names=frozenset(compiler.names),
        paths=frozenset(compiler.paths),
        calls=frozenset(compiler.calls),
    )


def check_expr(source: str, allowed_names: set[str] | frozenset[str] | None = None) -> str | None:
    """只检查不运行：正确返回 None，错误返回中文提示（网站表达式输入框实时检查用）。"""
    try:
        compile_expr(source, allowed_names)
    except ExprError as exc:
        return str(exc)
    return None
