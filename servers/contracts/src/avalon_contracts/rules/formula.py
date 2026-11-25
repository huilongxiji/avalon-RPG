"""公式：伤害、减伤、强化费用、掉率、签到体力、升级经验……每个公式有名字，内容是表达式。"""

from __future__ import annotations

from pydantic import BaseModel, Field

# 战斗内核会用到的公式。规则库里必须都有（默认值与旧版代码一致，见 avalon_logic.rules.builtin）。
BATTLE_FORMULAS: dict[str, str] = {
    "def_after_pen": "穿透后的有效防御",
    "physical_mitigation": "物理减伤系数",
    "physical_damage": "物理伤害",
    "resist_after_pen": "穿透后的有效法抗",
    "level_reduce": "等级系数和免伤（法术伤害、真实伤害用）",
    "level_coef_taken": "等级压制：怪物受到的伤害",
    "level_coef_dealt": "等级压制：怪物造成的伤害",
    "scale_dealt": "怪物造成的伤害乘等级压制",
    "effective_level": "祝福后参与计算的怪物等级",
    "crit_hit": "暴击后的伤害",
    "amplify": "增伤",
    "lessen": "伤害按百分比降低",
    "shield_overflow": "护盾被打穿后漏过的伤害",
    "first_strike": "是否先手",
    "precision_crit": "精准：敏捷比带来的暴击率",
    "precision_crit_dmg": "精准：敏捷比带来的暴击伤害",
    "precision_pen_pct": "精准：无视防御（含保底）",
    "precision_flat_pen": "精准：敏捷低于目标时的物理穿透",
    "world_boss_atk": "世界BOSS每回合的攻击",
}
GAME_FORMULAS = {
    'enhance_step_cost': '强化单级费用', 'enhance_success': '强化成功率',
    'enhance_stat_mult': '强化属性倍率', 'checkin_stamina': '签到体力',
    'exp_to_next': '升级所需经验', 'pity_threshold': '副本保底阈值', 'market_fee': '市场手续费',
}
REQUIRED_FORMULAS = (*BATTLE_FORMULAS, *GAME_FORMULAS)

# 保留原导入名；这些 M4 公式现已实现，并且属于必需公式。
PLANNED_FORMULAS = (
    "enhance_step_cost",      # 强化单级费用
    "enhance_success",        # 强化成功率
    "enhance_stat_mult",      # 强化属性倍率
    "checkin_stamina",        # 签到体力
    "exp_to_next",            # 升级所需经验
    "pity_threshold",         # 保底阈值
    "market_fee",             # 市场手续费
)


class FormulaDef(BaseModel):
    # 公式代号：写在表达式里调用它（公式名(值, …)），可以用中文，不能以数字或下划线开头
    name: str = Field(pattern=r"^[^\W\d_]\w*$", max_length=64)
    title: str = ""                         # 中文名称（展示用；内置公式不填就用 BATTLE_FORMULAS 里的）
    expr: str = Field(min_length=1)
    # 这个公式可以用的变量名及说明，例如 {"defense": "有效防御", "level": "攻击方等级"}
    params: dict[str, str] = Field(default_factory=dict)
    description: str = ""
