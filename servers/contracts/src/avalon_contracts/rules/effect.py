"""效果：在什么时机、满足什么条件、执行哪些动作。

装备技能全部用这个格式表达（设计文档 7.4–7.6 节），不设脚本效果。
时机和动作的种类由引擎提供；新增种类要改一次引擎代码，之后所有装备都能用。

一个效果由四部分组成，都可以省略：
- params：数值参数。网站上调数值只改这里，描述文字和逻辑自动跟着变；
- static：静态加成，汇总面板属性时生效（穿上就有）；
- auras：战斗中持续生效的加成/削弱，数值随战斗状态实时计算（比如"目标每层碎晶降低 1% 防御"）；
- triggers：触发逻辑，在某个时机满足条件时执行一组动作。
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 战斗时机
TRIGGERS: dict[str, str] = {
    "battle_start": "战斗开始",
    "round_start": "回合开始",
    "before_action": "出手前",
    "attack": "生成这次普通攻击（可以把普通攻击换成指定的一段或多段攻击）",
    "compute_hit": "计算这次攻击的伤害（可以给这次攻击追加伤害）",
    "segment": "多段攻击的每一段命中后（可以提升这一段的伤害）",
    "on_hit": "攻击命中后（没被闪避；伤害结算前，可以提升这次攻击的伤害）",
    "on_crit": "攻击暴击后",
    "after_attack": "攻击结算后",
    "on_dodge": "闪避了对方的攻击后",
    "taking_hit": "受到攻击、伤害结算前（护盾吸收之后，可以减少这次伤害）",
    "damage_taken": "受到对方攻击后",
    "hp_below": "血量下降后（用条件写阈值）",
    "fatal": "受到致命伤害时（可以用「取消」免疫这次伤害）",
    "before_damage": "受到攻击、扣血前（免疫致命伤害之后，可以减少这次伤害）",
    "shield_break": "护盾被打破",
    "stack_full": "层数即将叠满（可以取消这次叠层）",
    "stack_gain": "层数增加后",
    "kill": "击杀敌人",
    "dealt_damage": "造成伤害后（普通攻击或效果造成的伤害）",
    "round_end": "回合结束",
    "battle_end": "战斗结束",
}

# 引擎提供的动作
ACTIONS: dict[str, str] = {
    "modify_stat": "改属性（可限时）",
    "damage": "额外造成一段伤害",
    "replace_hit": "把这次普通攻击换成指定的一段或多段攻击",
    "extra_hit": "追加一段攻击",
    "set_hit": "给这次攻击追加一部分伤害（和这次攻击合在一起结算）",
    "scale_hit": "这次攻击（或多段攻击的这一段）的伤害提升至百分之几（不含真实伤害）",
    "reduce_hit": "减少这次受到的伤害",
    "chase": "追击：按递减的比例追加伤害，追击暴击时继续追击（可连锁）",
    "execute": "斩杀目标（生命直接降到 0）",
    "lose_hp": "自己扣血（不算受到伤害，最低保留 1 点生命）",
    "heal": "治疗",
    "shield": "加护盾",
    "stack": "改层数",
    "status": "施加状态",
    "prevent": "取消当前事件",
    "flag": "记标记（本场战斗内有效）",
    "carry": "记标记并跨场保留（爬塔、连战）",
    "note": "写战报说明",
    "random": "从几组动作里随机选一组执行",
}

# 汇总面板属性时的静态加成方式
StaticOp = Literal["add", "add_pct", "max", "mul", "set"]
STATIC_OPS = {
    "add": "加固定值（在百分比加成之后加）",
    "add_pct": "加百分比（与其他百分比相加后一起乘）",
    "max": "加固定值，但多个来源（同一组）只取最大的一个（与旧版套装的合并方式一致）",
    "mul": "乘以",
    "set": "设为",
}

# 战斗中的加成/削弱方式。计算顺序固定：
#   1. 当前值 + 所有 add + 所有 add_base_pct（按基础值算）
#   2. 扣固定值 down，再按 down_pct 的总和打折：max(0, 值 - 固定) × (100 - 百分比合计) // 100
#   3. 每个 down_pct_each 单独再打一次折
#   4. 每个 mul_pct 依次乘 (100 + 值)%
#   5. 按属性定义的上下限截断
BattleOp = Literal["add", "add_base_pct", "down", "down_pct", "down_pct_each", "mul_pct"]
BATTLE_OPS = {
    "add": "加固定值",
    "add_base_pct": "按基础值加百分比",
    "down": "减固定值",
    "down_pct": "减百分比（与其他减百分比相加）",
    "down_pct_each": "单独再减百分比",
    "mul_pct": "乘以 (100 + 值)%",
}
# modify_stat 用 scope="panel" 时直接改面板（比如属性翻倍），可用的方式
PanelOp = Literal["add", "mul", "set"]

Target = Literal["self", "foe"]


class StaticMod(BaseModel):
    """静态加成：穿上就生效，比如 +5% 免伤。value 可以是数字或表达式。"""

    model_config = ConfigDict(populate_by_name=True)

    stat: str
    op: StaticOp = "add"
    value: float | str
    if_: str | None = Field(default=None, alias="if")      # 条件，比如只对法术武器生效
    group: str | None = None    # op 为 max 时：同一属性、同一组里只取最大的一个（不写就是这个属性的默认组）


class AuraMod(BaseModel):
    """战斗中持续生效的加成/削弱，数值每次用到时实时计算。"""

    model_config = ConfigDict(populate_by_name=True)

    target: Target = "self"
    stat: str
    op: BattleOp = "add"
    value: float | str
    if_: str | None = Field(default=None, alias="if")


class ActionSpec(BaseModel):
    """一个动作。除 action 和 if 外的字段按动作种类不同而不同（target、value、kind……）。"""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    action: str
    if_: str | None = Field(default=None, alias="if")      # 这个动作自己的条件，可省略

    @field_validator("action")
    @classmethod
    def _known_action(cls, value: str) -> str:
        if value not in ACTIONS:
            raise ValueError(f"未知的动作：{value}")
        return value

    def args(self) -> dict[str, Any]:
        return dict(self.model_extra or {})


class TriggerSpec(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    on: str
    if_: str | None = Field(default=None, alias="if")       # 条件表达式
    chance: float | str | None = None                       # 触发概率 0–100，可为表达式
    once: Literal["battle", "run"] | None = None            # 每场一次 / 每次挑战一次
    cooldown: int = Field(default=0, ge=0)                  # 冷却回合数
    priority: int = 100                                     # 同一时机里小的先执行
    stack: str | None = None                                # 层数类时机只对这种层数生效
    do: list[ActionSpec] = Field(min_length=1)

    @field_validator("on")
    @classmethod
    def _known_trigger(cls, value: str) -> str:
        if value not in TRIGGERS:
            raise ValueError(f"未知的时机：{value}")
        return value


_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?::(coef|permille|cn))?\}")


def format_number(value: float) -> str:
    """数值显示：整数不带小数点，小数去掉末尾的 0。"""
    value = round(float(value), 6)
    return str(int(value)) if value.is_integer() else f"{value:g}"


_CN_DIGITS = "零一二三四五六七八九"


def _cn_number(n: int) -> str:
    """0~99 写成中文数字（第五回合、第十二回合），其余照常写数字。"""
    if not 0 <= n < 100:
        return str(n)
    if n < 10:
        return _CN_DIGITS[n]
    tens, ones = divmod(n, 10)
    return ("" if tens == 1 else _CN_DIGITS[tens]) + "十" + (_CN_DIGITS[ones] if ones else "")


class EffectDef(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_\-]+$")
    name: str
    # 描述模板：{参数名} 显示参数原值；{参数名:coef} 显示为系数（参数是百分数，6 显示成 0.06）；
    # {参数名:permille} 按千分数显示（75 显示成 0.075）
    desc: str = ""
    params: dict[str, float] = Field(default_factory=dict)
    static: list[StaticMod] = Field(default_factory=list)
    auras: list[AuraMod] = Field(default_factory=list)
    triggers: list[TriggerSpec] = Field(default_factory=list)

    def render_desc(self) -> str:
        """用参数填好描述模板，生成中文说明文字。

        {p} 写数值；{p:coef} 写成系数（60 → 0.6）；{p:permille} 按千分写（65 → 0.065）；{p:cn} 写中文数字（5 → 五）。
        """

        def repl(match: re.Match[str]) -> str:
            key, style = match.group(1), match.group(2)
            if key not in self.params:
                return match.group(0)
            value = float(self.params[key])
            if style is None:
                return format_number(value)
            if style == "cn":
                return _cn_number(int(value))
            value /= 100 if style == "coef" else 1000
            # 系数是整数时写成 2.0、1.0（与图鉴原文一致）
            return f"{value:.1f}" if round(value, 6).is_integer() else format_number(value)

        return _PLACEHOLDER.sub(repl, self.desc)
