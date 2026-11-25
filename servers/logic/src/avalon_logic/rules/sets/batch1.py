"""M3 批次 1：只加属性但合并方式特殊的（取最大、只对精准武器生效）、开场护盾、受到伤害提高、
攻击后追加一段真实伤害、按损失血量加攻击。

数值与旧版图鉴一致；用哪种属性与旧版一一对应（见 rules/samples.py 开头的说明）。
效果名称：多档套装写"套装名·N件"，只有一档的直接写套装名（迁移工具按名称对应到套装档位）。
"""

from __future__ import annotations

from avalon_contracts.rules.effect import EffectDef

_DONE = "not hit.dodged and hit.damage > 0"
_DONE_ALIVE = _DONE + " and foe.hp_now > 0"


def _shield(var: str, param: str, merge: str = "sum") -> dict:
    """登记开场护盾的比例（由全局机制"开场护盾"统一计算）。法力护盾相加，生命/防御护盾取最大。"""
    value = f"self.vars.{var} + {param}" if merge == "sum" else f"max(self.vars.{var}, {param})"
    return {"action": "flag", "name": var, "value": value}


SUIKONG_2 = EffectDef.model_validate({
    "id": "suikong_2",
    "name": "碎空·2件",
    "desc": "战斗开始时，获得（{shield_mp_pct:coef}*法力）护盾。",
    "params": {"shield_mp_pct": 60},
    "triggers": [{"on": "battle_start", "priority": 5, "do": [_shield("开场护盾_法力", "shield_mp_pct")]}],
})

LENGJING_XUANGUANG_2 = EffectDef.model_validate({
    "id": "lengjing_xuanguang_2",
    "name": "棱镜炫光·2件",
    "desc": "提升{pen}法术穿透。战斗开始时，获得（{shield_mp_pct:coef}*法力）护盾。",
    "params": {"pen": 15, "shield_mp_pct": 100},
    "static": [{"stat": "ignore_magic_resist", "op": "add", "value": "pen"}],
    "triggers": [{"on": "battle_start", "priority": 5, "do": [_shield("开场护盾_法力", "shield_mp_pct")]}],
})

LIULI_ZHIXIN = EffectDef.model_validate({
    "id": "liuli_zhixin",
    "name": "琉璃之心",
    "desc": "获得（{def_atk_pct:coef}*攻击+{def_mp_pct:coef}*法力）防御。战斗开始时，获得"
            "（{shield_hp_pct:coef}*生命+{shield_def_pct:coef}*防御）护盾。",
    "params": {"def_atk_pct": 12, "def_mp_pct": 4, "shield_hp_pct": 25, "shield_def_pct": 150},
    # 按属性换算的加成：多个套装都有时叠加（2026-11-24 按图鉴修正；旧版只取最大的一个）
    "static": [{"stat": "defense", "op": "add", "value": "self.base.atk * def_atk_pct // 100"},
               {"stat": "defense", "op": "add", "value": "self.base.mp * def_mp_pct // 100"}],
    "triggers": [{"on": "battle_start", "priority": 5, "do": [
        _shield("开场护盾_生命", "shield_hp_pct", "max"),
        _shield("开场护盾_防御", "shield_def_pct", "max"),
    ]}],
})

# 按图鉴修正（2026-11-23 决定）：旧版 bot 里只有攻击 +10% 生效，"无视防御"从没被用到。
# 旧版的字段名是"物理无视防御"，所以只加物理攻击的无视防御（pen_pct），不影响法术。
YUJIN_WANGCHAO_2 = EffectDef.model_validate({
    "id": "yujin_wangchao_2",
    "name": "余烬王朝·2件",
    "desc": "提升{atk_pct}%无视防御和攻击。",
    "params": {"atk_pct": 10, "ignore_def_pct": 10},
    "static": [{"stat": "atk", "op": "add_pct", "value": "atk_pct"},
               {"stat": "pen_pct", "op": "add", "value": "ignore_def_pct"}],
})

RONGHUO_ZHINU_2 = EffectDef.model_validate({
    "id": "ronghuo_zhinu_2",
    "name": "熔火之怒·2件",
    "desc": "提升{pen_pct}%无视防御和{crit_dmg}%暴击伤害",
    "params": {"pen_pct": 10, "crit_dmg": 15},
    "static": [
        # 旧版这里的"无视防御"是精准增益：只对精准武器生效
        {"stat": "pen_pct", "op": "add", "value": "pen_pct", "if": "weapon.precision"},
        {"stat": "precision_pen_pct", "op": "add", "value": "pen_pct", "if": "weapon.precision"},
        {"stat": "crit_dmg", "op": "add", "value": "crit_dmg"},
    ],
})

SHENYUAN_NINGSHI = EffectDef.model_validate({
    "id": "shenyuan_ningshi",
    "name": "深渊凝视",
    "desc": "受到的伤害增加（{taken_mp_pct:coef}*法力）%，提升{ignore_pct}%无视防御和无视法抗",
    "params": {"taken_mp_pct": 10, "ignore_pct": 20},
    "static": [
        {"stat": "ignore_def_pct", "op": "max", "value": "ignore_pct"},
        {"stat": "ignore_resist_pct", "op": "max", "value": "ignore_pct"},
    ],
    "auras": [{"target": "self", "stat": "dmg_taken_pct", "op": "add", "value": "self.panel.mp * taken_mp_pct // 100"}],
})

QIANXING_RONGJIN = EffectDef.model_validate({
    "id": "qianxing_rongjin",
    "name": "千星熔烬",
    "desc": "提升{crit_dmg}%暴击伤害。每次普攻后额外造成（{true_agi_pct:coef}*敏捷）真实伤害。",
    "params": {"crit_dmg": 30, "true_agi_pct": 30},
    "static": [{"stat": "crit_dmg", "op": "add", "value": "crit_dmg"}],
    "triggers": [{"on": "after_attack", "priority": 50, "if": _DONE_ALIVE, "do": [
        {"action": "damage", "kind": "true", "value": "self.panel.agi * true_agi_pct // 100", "label": "千星熔烬"},
    ]}],
})

GENXU_LIESHA_4 = EffectDef.model_validate({
    "id": "genxu_liesha_4",
    "name": "根须猎杀·4件",
    "desc": "提升{crit}%暴击率。攻击后有{chance}%概率追击造成（{agi_pct:coef}*敏捷）真实伤害",
    "params": {"crit": 20, "chance": 40, "agi_pct": 60},
    "static": [{"stat": "crit", "op": "add", "value": "crit"}],
    "triggers": [{"on": "after_attack", "priority": 60, "if": _DONE_ALIVE, "chance": "chance", "do": [
        {"action": "damage", "kind": "true", "value": "self.panel.agi * agi_pct // 100", "label": "根须猎杀"},
    ]}],
})

HUOWEN = EffectDef.model_validate({
    "id": "huowen",
    "name": "火纹",
    "desc": "提升{dmg_pct}%增伤。攻击后额外造成（{atk_pct:coef}攻击+{mp_pct:coef}法力）真实伤害。",
    "params": {"dmg_pct": 8, "atk_pct": 10, "mp_pct": 5},
    "static": [{"stat": "dmg_pct", "op": "max", "value": "dmg_pct"}],
    "triggers": [{"on": "after_attack", "priority": 70, "if": _DONE_ALIVE, "do": [
        {"action": "damage", "kind": "true",
         "value": "self.panel.atk * atk_pct // 100 + self.panel.mp * mp_pct // 100", "label": "火纹"},
    ]}],
})

WUGUANG_SHENYUAN_4 = EffectDef.model_validate({
    "id": "wuguang_shenyuan_4",
    "name": "无光深渊·4件",
    "desc": "每损失10%的生命，攻击力增加{atk_pct}%",
    "params": {"atk_pct": 15},
    "auras": [{"target": "self", "stat": "atk", "op": "add", "if": "self.hp_now < self.hp_max",
               "value": "self.base.atk * ((self.hp_max - self.hp_now) * 10 // self.hp_max) * atk_pct // 100"}],
})

BATCH1 = [SUIKONG_2, LENGJING_XUANGUANG_2, LIULI_ZHIXIN, YUJIN_WANGCHAO_2, RONGHUO_ZHINU_2, SHENYUAN_NINGSHI,
          QIANXING_RONGJIN, GENXU_LIESHA_4, HUOWEN, WUGUANG_SHENYUAN_4]
