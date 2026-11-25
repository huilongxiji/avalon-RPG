"""M2 试写的 5 个套装效果（数值与旧版图鉴一致）。

用来验证效果数据格式够不够表达现有机制：开场限时增益、召唤物追加攻击、给目标叠层、
叠满爆发（取消叠层）、首次达到层数触发、回合结束护盾、低血阈值触发（每次挑战一次）、
概率触发、随机翻倍属性。M3 的迁移工具会把全部 70 个套装写成同样的格式导入规则库。

描述模板里 {参数:coef} 表示把百分数参数显示成系数（6 → 0.06）。
系数类参数一律存成整数百分数（和旧版一致），计算时写成「属性 * 参数 // 100」，
这样整除结果与旧版逐位相同，不会出现 0.29*100=28.999… 这类小数误差。

用哪种属性也与旧版一一对应：旧版直接用 player.x 的地方写 self.panel.x（开战时的面板值），
旧版用 _effective_xxx / _battle_agi 这类"战斗中的值"的地方写 self.x（含战斗中的加成）。
"""

from __future__ import annotations

from avalon_contracts.rules.effect import EffectDef
from avalon_contracts.rules.item import SetDef, SetTier

_DAMAGE_DONE = "not hit.dodged and hit.damage > 0"

QIANXING_HUANLONG = EffectDef.model_validate({
    "id": "qianxing_huanlong",
    "name": "千星唤龙",
    "desc": "提升{pen}法术穿透。战斗开始时，召唤一个拥有（{dragon_mp_pct:coef}*法力）攻击的火龙。"
            "每当你进行攻击后会追加1次物理伤害。",
    "params": {"pen": 8, "dragon_mp_pct": 6},
    "static": [{"stat": "ignore_magic_resist", "op": "add", "value": "pen"}],
    "triggers": [
        {   # 召唤火龙：记下火龙的攻击，跨场保留（爬塔连战时火龙一直在）
            "on": "battle_start", "priority": 20,
            "do": [{"action": "carry", "name": "火龙攻击", "value": "self.panel.mp * dragon_mp_pct // 100"}],
        },
        {   # 每次攻击造成伤害后，火龙追加一次物理伤害（吃防御，不吃穿透、暴击、增伤）
            "on": "after_attack", "priority": 10,
            "if": "self.vars.火龙攻击 > 0 and " + _DAMAGE_DONE,
            "do": [{"action": "damage", "kind": "physical", "value": "self.vars.火龙攻击", "label": "火龙"}],
        },
    ],
})

YINYOU_ZHIGE = EffectDef.model_validate({
    "id": "yinyou_zhige",
    "name": "吟游之歌",
    "desc": "获得（{agi_mp_pct:coef}*法力）敏捷。战斗开始时，提升{open_mp_pct}%法力和{open_def_pct}%防御，"
            "持续{open_rounds}回合。造成法术伤害后施加1层碎晶，碎晶叠满后立即移除全部碎晶并造成"
            "（{burst_mp_pct:coef}*法力）物理伤害",
    "params": {"agi_mp_pct": 10, "open_mp_pct": 10, "open_def_pct": 20, "open_rounds": 3, "burst_mp_pct": 200},
    "static": [{"stat": "agi", "op": "add", "value": "self.base.mp * agi_mp_pct // 100"}],
    "triggers": [
        {
            "on": "battle_start",
            "do": [
                {"action": "modify_stat", "stat": "mp", "op": "add_base_pct", "value": "open_mp_pct",
                 "rounds": "open_rounds"},
                {"action": "modify_stat", "stat": "defense", "op": "mul_pct", "value": "open_def_pct",
                 "rounds": "open_rounds"},
            ],
        },
        {
            "on": "on_hit", "if": "hit.magic and hit.damage > 0",
            "do": [{"action": "stack", "name": "碎晶", "op": "add", "value": 1}],
        },
        {   # 任何来源的碎晶将要叠满时：取消这次叠层，清空碎晶并爆发（其他套装的"叠层并追加伤害"也随之取消追加）
            "on": "stack_full", "stack": "碎晶", "priority": 10,
            "do": [
                {"action": "prevent"},
                {"action": "stack", "name": "碎晶", "op": "clear"},
                {"action": "damage", "kind": "physical", "value": "self.mp * burst_mp_pct // 100",
                 "label": "吟游之歌·碎晶爆发"},
            ],
        },
    ],
})

POJING_ZHILU = EffectDef.model_validate({
    "id": "pojing_zhilu",
    "name": "破镜之路",
    "desc": "每次攻击有{chance}%概率施加1层碎晶并额外造成（{agi_dmg_pct:coef}*敏捷）物理伤害，"
            "回合结束时每1层碎晶获得（{shield_atk_pct:coef}*攻击+{shield_agi_pct:coef}*敏捷）护盾。"
            "当目标首次拥有{cap_stacks}层碎晶时，获得{cap_reduce}%免伤并造成（{cap_true_agi_pct:coef}*敏捷）真实伤害。",
    "params": {"chance": 66, "agi_dmg_pct": 60, "shield_atk_pct": 1, "shield_agi_pct": 2,
               "cap_stacks": 6, "cap_reduce": 10, "cap_true_agi_pct": 100},
    "triggers": [
        {
            "on": "after_attack", "priority": 30, "if": _DAMAGE_DONE, "chance": "chance",
            "do": [
                {"action": "stack", "name": "碎晶", "op": "add", "value": 1},
                {"action": "damage", "kind": "physical", "value": "self.panel.agi * agi_dmg_pct // 100",
                 "label": "破镜之路", "if": "not last.prevented"},
            ],
        },
        {
            "on": "round_end", "if": "foe.stacks.碎晶 > 0",
            "do": [{"action": "shield",
                    "value": "(self.panel.atk * shield_atk_pct + self.panel.agi * shield_agi_pct) // 100 * foe.stacks.碎晶"}],
        },
        {
            "on": "stack_gain", "stack": "碎晶", "once": "battle", "if": "foe.stacks.碎晶 >= cap_stacks",
            "do": [
                {"action": "damage", "kind": "true", "value": "self.panel.agi * cap_true_agi_pct // 100",
                 "label": "破镜之路·碎晶叠满"},
                {"action": "modify_stat", "stat": "dmg_reduce", "op": "add", "value": "cap_reduce"},
            ],
        },
    ],
})

HUANSHEN_JIATUI = EffectDef.model_validate({
    "id": "huanshen_jiatui",
    "name": "幻身假蜕",
    "desc": "战斗开始时，提升{open_reduce}%免伤，持续{open_rounds}回合，当生命低于{low_hp_pct}%时提升"
            "{crit_bonus}%暴击率，持续{crit_rounds}回合。造成精准伤害后有{chance}%概率施加1层碎晶"
            "并额外造成（{atk_pct:coef}*攻击+{agi_pct:coef}*敏捷）物理伤害。",
    "params": {"open_reduce": 10, "open_rounds": 5, "low_hp_pct": 60, "crit_bonus": 30, "crit_rounds": 4,
               "chance": 66, "atk_pct": 20, "agi_pct": 40},
    "triggers": [
        {
            "on": "battle_start",
            "do": [{"action": "modify_stat", "stat": "dmg_reduce", "op": "add", "value": "open_reduce",
                    "rounds": "open_rounds"}],
        },
        {   # 每次挑战只触发一次（爬塔连战跨场保留触发记录）
            "on": "hp_below", "once": "run", "if": "self.hp_now * 100 < self.hp_max * low_hp_pct",
            "do": [
                {"action": "modify_stat", "stat": "crit", "op": "add", "value": "crit_bonus",
                 "rounds": "crit_rounds"},
                {"action": "note", "text": "幻身假蜕：暴击+{crit_bonus}%·{crit_rounds}回合"},
            ],
        },
        {
            "on": "after_attack", "priority": 40, "if": _DAMAGE_DONE + " and hit.precision", "chance": "chance",
            "do": [
                {"action": "stack", "name": "碎晶", "op": "add", "value": 1},
                {"action": "damage", "kind": "physical",
                 "value": "self.panel.atk * atk_pct // 100 + self.panel.agi * agi_pct // 100",
                 "label": "幻身假蜕", "if": "not last.prevented"},
            ],
        },
    ],
})

LINGZHI_ZHUFU = EffectDef.model_validate({
    "id": "lingzhi_zhufu",
    "name": "翎之祝福",
    "desc": "战斗开始时，随机一项基础属性翻倍",
    "triggers": [{
        "on": "battle_start", "priority": 0,
        "do": [{"action": "random", "choices": [
            {"label": f"{label}翻倍",
             "do": [{"action": "modify_stat", "scope": "panel", "stat": stat, "op": "mul", "value": 2}]}
            for stat, label in (("hp", "生命"), ("atk", "攻击"), ("defense", "防御"), ("agi", "敏捷"), ("mp", "法力"))
        ]}],
    }],
})

TRIAL_EFFECTS = [QIANXING_HUANLONG, YINYOU_ZHIGE, POJING_ZHILU, HUANSHEN_JIATUI, LINGZHI_ZHUFU]
# 这 5 个套装在旧版图鉴里都是 1 件生效
TRIAL_SETS = [SetDef(name=e.name, tiers=[SetTier(pieces=1, effects=[e.id])]) for e in TRIAL_EFFECTS]
