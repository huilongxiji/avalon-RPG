"""从当前规则版本读取游戏参数，默认值用于尚未加载规则的纯计算和旧版本兼容。"""

from __future__ import annotations

from functools import lru_cache

from avalon_contracts.errors import GameError

from ..engine.expr import ExprRuntimeError, compile_expr
from ..rules import current
from ..rules.game_defaults import DEFAULTS, FORMULAS


def value(key: str):
    rules = current.get()
    return rules.setting(key, DEFAULTS[key]) if rules else DEFAULTS[key]


@lru_cache(maxsize=None)
def _fallback(name: str):
    definition = next(f for f in FORMULAS if f.name == name)
    return compile_expr(definition.expr, frozenset(definition.params))


def formula(name: str, **values) -> int | float:
    rules = current.get()
    try:
        result = rules.formulas[name](**values) if rules and name in rules.formulas else _fallback(name).number(values)
    except (ExprRuntimeError, ArithmeticError) as exc:
        raise GameError('rules_invalid', '游戏公式计算失败，请联系管理员检查规则', formula=name) from exc
    if result < 0:
        raise GameError('rules_invalid', '游戏公式不能返回负数', formula=name)
    if name in ('exp_to_next', 'pity_threshold', 'enhance_step_cost') and result < 1:
        raise GameError('rules_invalid', '经验、保底阈值和强化费用必须至少为 1', formula=name)
    return result
