"""内置的默认规则：属性、层数、公式、设定、全局机制。

这些是规则库第一个版本的初始内容，数值和取整方式与旧版 bot（old_data/src/plugins/dungeon/combat.py、
catalog.py）逐条一致，由对拍测试保证。之后在网站上修改的是规则库里的数据，不是这个文件；
这里只在规则库还是空的时候用来生成第一个版本。
"""

from __future__ import annotations

from avalon_contracts.rules.effect import EffectDef
from avalon_contracts.rules.formula import FormulaDef
from avalon_contracts.rules.setting import SettingDef
from avalon_contracts.rules.stack import StackDef
from avalon_contracts.rules.stat import StatDef

from .game_defaults import FORMULAS as GAME_FORMULAS
from .game_defaults import SETTINGS as GAME_SETTINGS

# ---------------------------------------------------------------- 属性

STATS: list[StatDef] = [
    StatDef(key="hp", name="生命", min=1),
    StatDef(key="atk", name="攻击", min=0),
    StatDef(key="defense", name="防御", min=0),
    StatDef(key="agi", name="敏捷", min=0),
    StatDef(key="mp", name="法力", min=0),
    StatDef(key="crit", name="暴击率", min=0, max=100, percent=True),
    StatDef(key="crit_dmg", name="暴击伤害", default=150, min=0, percent=True),
    StatDef(key="dodge", name="闪避率", min=0, max=100, percent=True),
    StatDef(key="penetration", name="物理穿透"),
    StatDef(key="pen_pct", name="无视防御", percent=True),
    StatDef(key="ignore_def_pct", name="额外无视防御", percent=True),
    StatDef(key="ignore_magic_resist", name="法术穿透"),
    StatDef(key="ignore_resist_pct", name="无视法抗", percent=True),
    StatDef(key="magic_resist", name="法抗", min=0),
    StatDef(key="dmg_reduce", name="免伤", percent=True),
    StatDef(key="dmg_pct", name="增伤", percent=True),
    StatDef(key="dmg_taken_pct", name="受到伤害提高", percent=True, show=False),
    StatDef(key="magic_taken_pct", name="受到的法术伤害提升", percent=True, show=False),
    # 幸运三角的加成：对玩家造成的全部伤害生效（单独增伤不作用于真实伤害）
    StatDef(key="extra_dmg_mul_pct", name="单独增伤（全部伤害）", percent=True, show=False),
    # 记账用：无视防御里来自"只对精准武器生效"的部分（已经含在无视防御里，属性翻倍时这部分不翻倍）
    StatDef(key="precision_pen_pct", name="其中精准武器的无视防御", percent=True, show=False),
    StatDef(key="extra_ignore_def_pct", name="额外无视防御（全部物理伤害）", percent=True, show=False),
    StatDef(key="extra_ignore_resist_pct", name="额外无视法抗（全部法术伤害）", percent=True, show=False),
    StatDef(key="dmg_dealt_down", name="造成伤害降低", percent=True, show=False),
    StatDef(key="dmg_taken_down", name="受到伤害降低", percent=True, show=False),
    StatDef(key="fire_cap", name="火痕上限", show=False),
    StatDef(key="magic_crit_rate", name="法术暴击率", min=0, max=100, percent=True, show=False),
    StatDef(key="bless_level", name="祝福等级", show=False),
    # 百分比加成类：汇总面板时加到对应属性上（对应关系在设定 percent_stats 里）
    StatDef(key="hp_pct", name="生命加成", percent=True),
    StatDef(key="atk_pct", name="攻击加成", percent=True),
    StatDef(key="defense_pct", name="防御加成", percent=True),
    StatDef(key="agi_pct", name="敏捷加成", percent=True),
    StatDef(key="mp_pct", name="法力加成", percent=True),
    # 不参与战斗的装备加成
    StatDef(key="exp_pct", name="经验加成", percent=True),
    StatDef(key="drop_pct", name="装备掉率", percent=True),
]

# ---------------------------------------------------------------- 层数

STACKS: list[StackDef] = [
    StackDef(key="碎晶", name="碎晶", owner="foe", max=6, carry=False, boss_immune=True),
    # 千丝引：上限由效果自己的参数控制（叠满的下一次攻击清空并爆发）
    StackDef(key="千丝", name="千丝", owner="foe", max=None, carry=False, boss_immune=False),
    # 元素洗礼（暴击后减防，上限由效果参数控制）、元素之心（削抗）、千机令、沉沦的印记：旧版世界BOSS也会叠
    StackDef(key="洗礼", name="洗礼", owner="foe", max=None, carry=False, boss_immune=False),
    StackDef(key="削抗", name="削抗", owner="foe", max=None, carry=False, boss_immune=False),
    StackDef(key="千机印记", name="千机印记", owner="foe", max=None, carry=False, boss_immune=False),
    StackDef(key="沉沦印记", name="沉沦印记", owner="foe", max=None, carry=False, boss_immune=False),
    # 上限写在套装参数里（叠层时取较小值）
    StackDef(key="根蚀", name="根蚀", owner="foe", max=None, carry=False, boss_immune=True),
    StackDef(key="腐朽", name="腐朽", owner="foe", max=None, carry=False, boss_immune=True),
    StackDef(key="星印", name="星印", owner="foe", max=None, carry=False, boss_immune=False),
    StackDef(key="蚀甲", name="蚀甲", owner="foe", max=None, carry=False, boss_immune=False),
    StackDef(key="星盘削抗", name="星盘削抗", owner="foe", max=None, carry=False, boss_immune=False),
    StackDef(key="风蚀", name="风蚀", owner="foe", max=None, carry=False, boss_immune=True),
    # 火痕：默认上限 7 层，施加者的"火痕上限"属性大于 0 时用它（天火九舞 9 层、阳炎庇护 15 层）
    StackDef(key="火痕", name="火痕", owner="foe", max=7, max_stat="fire_cap", carry=False, boss_immune=True),
]

# ---------------------------------------------------------------- 公式


def _f(name: str, expr: str, params: dict[str, str], description: str) -> FormulaDef:
    return FormulaDef(name=name, expr=expr, params=params, description=description)


FORMULAS: list[FormulaDef] = [
    _f("def_after_pen",
       "max(0, max(0, defense - max(0, pen)) * (100 - min(100, max(0, pen_pct))) // 100)",
       {"defense": "目标当前防御", "pen": "物理穿透", "pen_pct": "无视防御%"},
       "先减物理穿透，再按无视防御打折"),
    _f("physical_mitigation",
       "1 - defense / (defense + 30 + level * 2)",
       {"defense": "穿透后的有效防御", "level": "攻击方等级"},
       "物理减伤系数：防御越高、攻击方等级越低，减伤越多"),
    _f("physical_damage",
       "0 if atk <= 0 or min(100, reduce) >= 100 else max(1, floor(atk * mitigation * coef * (1 - min(100, reduce) / 100)))",
       {"atk": "攻击数值", "mitigation": "物理减伤系数", "coef": "等级系数", "reduce": "目标免伤%"},
       "物理伤害：攻击 × 减伤系数 × 等级系数 × (1 - 免伤)，至少 1 点"),
    _f("resist_after_pen",
       "max(0, max(0, resist) - max(0, pen)) * (100 - min(100, max(0, pen_pct))) // 100",
       {"resist": "目标当前法抗", "pen": "法术穿透", "pen_pct": "无视法抗%"},
       "先减法术穿透，再按无视法抗打折"),
    _f("level_reduce",
       "0 if value <= 0 or clamp(reduce, 0, 100) >= 100 else max(0, floor(value * coef * (1 - clamp(reduce, 0, 100) / 100)))",
       {"value": "伤害数值", "coef": "等级系数", "reduce": "目标免伤%"},
       "法术伤害（法力减法抗之后）和真实伤害：乘等级系数和 (1 - 免伤)"),
    _f("level_coef_taken",
       "max(0.0, 1.0 - 0.05 * (foe_level - level)) if foe_level > level else 1.0",
       {"level": "玩家等级", "foe_level": "怪物等级"},
       "怪物等级高于玩家时，每高 1 级怪物受到的伤害减少 5%"),
    _f("level_coef_dealt",
       "1.0 + 0.1 * (foe_level - level) if foe_level - level >= 6 else 1.0",
       {"level": "玩家等级", "foe_level": "怪物等级"},
       "怪物高出玩家 6 级及以上时，每级增加怪物 10% 的伤害"),
    _f("scale_dealt",
       "floor(value * coef) if coef > 1 else value",
       {"value": "怪物伤害", "coef": "等级系数"},
       "怪物造成的伤害乘等级系数"),
    _f("effective_level",
       "foe_level - min(bless, foe_level - level) if bless > 0 and foe_level > level else foe_level",
       {"level": "玩家等级", "foe_level": "怪物等级", "bless": "祝福等级"},
       "祝福：等级低于目标时，等级差按少算若干级参与计算"),
    _f("crit_hit",
       "max(1, value * (mult if mult > 0 else fallback) // 100)",
       {"value": "暴击前伤害", "mult": "暴击伤害%", "fallback": "默认暴击伤害%"},
       "暴击后的伤害"),
    _f("amplify",
       "value if pct <= 0 or value <= 0 else max(0, value * (100 + pct) // 100)",
       {"value": "伤害", "pct": "增伤%"},
       "增伤（真实伤害不吃增伤）"),
    _f("lessen",
       "value if value <= 0 or pct <= 0 else max(0, value * (100 - min(100, pct)) // 100)",
       {"value": "伤害", "pct": "降低%"},
       "伤害按百分比降低（造成伤害降低、受到伤害降低）"),
    _f("shield_overflow",
       "mitigated * overflow // raw",
       {"mitigated": "减伤后的伤害", "overflow": "打穿护盾后剩下的原始伤害", "raw": "原始伤害"},
       "护盾按原始伤害吸收，打穿后按比例漏过减伤后的伤害"),
    _f("first_strike",
       "agi >= foe_agi",
       {"agi": "玩家敏捷", "foe_agi": "怪物敏捷"},
       "敏捷不低于怪物时玩家先手"),
    _f("precision_crit",
       "0 if agi < foe_agi else (20 if foe_agi <= 0 else min(20, (agi * 100 // foe_agi - 100) // 5))",
       {"agi": "自己的敏捷", "foe_agi": "目标敏捷"},
       "精准：敏捷每超出目标 1%，暴击率 +0.2%，最多 +20%"),
    _f("precision_crit_dmg",
       "0 if agi < foe_agi else (50 if foe_agi <= 0 else min(50, (agi * 100 // foe_agi - 100) // 2))",
       {"agi": "自己的敏捷", "foe_agi": "目标敏捷"},
       "精准：敏捷每超出目标 1%，暴击伤害 +0.5%，最多 +50%"),
    _f("precision_pen_pct",
       "10 + (0 if agi < foe_agi else (20 if foe_agi <= 0 else min(20, (agi * 100 // foe_agi - 100) // 5)))",
       {"agi": "自己的敏捷", "foe_agi": "目标敏捷"},
       "精准：保底 10% 无视防御，敏捷每超出目标 1% 再 +0.2%，最多再 +20%"),
    _f("precision_flat_pen",
       "max(0, agi) // 4 if agi < foe_agi else 0",
       {"agi": "自己的敏捷", "foe_agi": "目标敏捷"},
       "精准：敏捷低于目标时，获得（0.25*敏捷）物理穿透"),
    _f("world_boss_atk",
       "atk * (100 + growth * (round_no - 1)) // 100",
       {"atk": "世界BOSS基础攻击", "round_no": "回合", "growth": "每回合增长%"},
       "世界BOSS的攻击每回合按基础攻击增长"),
]

# ---------------------------------------------------------------- 全局机制（对所有战斗生效）

GLOBAL_EFFECTS: list[EffectDef] = [
    EffectDef.model_validate({
        "id": "shatter_rules",
        "name": "碎晶",
        "desc": "目标每层碎晶降低{def_pct}%防御和{resist_pct}%法抗；叠满{cap}层时额外降低{cap_agi_pct}%敏捷，"
                "并在每回合开始时受到（{tick_def_pct:coef}*防御）真实伤害",
        "params": {"def_pct": 1, "resist_pct": 1, "cap": 6, "cap_agi_pct": 10, "tick_def_pct": 10},
        "auras": [
            {"target": "foe", "stat": "defense", "op": "down_pct", "value": "foe.stacks.碎晶 * def_pct"},
            {"target": "foe", "stat": "magic_resist", "op": "down_pct_each", "value": "foe.stacks.碎晶 * resist_pct"},
            {"target": "foe", "stat": "agi", "op": "down_pct", "value": "cap_agi_pct if foe.stacks.碎晶 >= cap else 0"},
        ],
        "triggers": [{
            "on": "round_start", "priority": 10,
            "if": "foe.stacks.碎晶 >= cap and foe.hp_now > 0",
            "do": [{"action": "damage", "kind": "true", "value": "foe.panel.defense * tick_def_pct // 100",
                    "label": "碎晶"}],
        }],
    }),
    EffectDef.model_validate({
        # 各套装在"战斗开始"（优先级小于 10）登记护盾比例：法力护盾的比例相加，生命/防御护盾取最大；
        # 这里统一计算：先把比例合起来再乘属性、取整（与旧版一致，各自取整再相加会差 1 点）
        "id": "opening_shield",
        "name": "开场护盾",
        "desc": "战斗开始时，按登记的比例获得（法力×比例 + 生命×比例 + 防御×比例）护盾",
        "triggers": [{
            "on": "battle_start", "priority": 10,
            "do": [
                {"action": "shield", "value": "self.panel.mp * self.vars.开场护盾_法力 // 100"},
                {"action": "shield", "value": "self.panel.hp * self.vars.开场护盾_生命 // 100"},
                {"action": "shield", "value": "self.panel.defense * self.vars.开场护盾_防御 // 100"},
            ],
        }],
    }),
    EffectDef.model_validate({
        # 旧版：目标攻击后，全部层数单段结算；吃法抗、不计算法术穿透和无视法抗；目标或自己已倒下则不结算
        "id": "fire_rules",
        "name": "火痕",
        "desc": "目标每次攻击后，按火痕层数受到（{atk_pct:coef}*攻击*层数+{mp_pct:coef}*法力*层数）法术伤害"
                "（不计算法术穿透和无视法抗）",
        "params": {"atk_pct": 6, "mp_pct": 6},
        "triggers": [{
            "on": "damage_taken", "priority": 900,
            "if": "foe.stacks.火痕 > 0 and foe.hp_now > 0 and self.hp_now > 0",
            "do": [{"action": "damage", "kind": "magic", "ignore_resist": 0, "label": "火痕",
                    "value": "(self.panel.atk * atk_pct + self.panel.mp * mp_pct) * foe.stacks.火痕 // 100"}],
        }],
    }),
    EffectDef.model_validate({
        "id": "magic_crit_mp",
        "name": "法术系：暴击转法力",
        "desc": "使用法术武器时，装备上每 5% 暴击率转化为 5% 法力",
        "static": [{"stat": "mp", "op": "add_pct", "value": "min(100, max(0, self.base.crit)) // 5 * 5",
                    "if": "weapon.magic"}],
    }),
]

# ---------------------------------------------------------------- 设定

SETTINGS: list[SettingDef] = [
    SettingDef(key="max_rounds", value=50, description="回合上限"),
    SettingDef(key="draw_idle_rounds", value=50, description="不限回合时，连续多少回合双方都没造成伤害算平局"),
    SettingDef(key="default_crit_dmg", value=150, description="暴击伤害为 0 时使用的默认暴击伤害（%）"),
    SettingDef(key="monster_default_dodge", value=5, description="怪物没填闪避率时的默认值（%）"),
    SettingDef(key="percent_stats", value={
        "hp_pct": "hp", "atk_pct": "atk", "defense_pct": "defense", "agi_pct": "agi", "mp_pct": "mp",
    }, description="百分比属性 → 它加成的属性"),
    SettingDef(key="global_effects", value=[e.id for e in GLOBAL_EFFECTS],
               description="对所有战斗都生效的效果"),
    SettingDef(key="world_boss", value={"hp": 10**12, "atk": 50, "atk_growth_pct": 5},
               description="世界BOSS：生命、攻击、每回合攻击增长%"),
]

# M4 的游戏公式/设定与战斗规则存入同一个版本。
FORMULAS.extend(GAME_FORMULAS)
SETTINGS.extend(GAME_SETTINGS)
