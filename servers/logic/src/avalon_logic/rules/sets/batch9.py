"""M3 批次 9：剩下的单件套装（千星狱火、王朝之徽、烬怒龙威、烬怒龙血、水纹、风纹、土纹、残存的翎之祝福、翎羽祝福）。

和旧版一致的规则：
- 受到攻击时（护盾吸收、幻象纹路减伤之后）依次结算：王朝之徽 → 烬怒龙血 → 千星狱火 → 守根哨卫 → 腐心咏叹。
- 受到攻击、扣血前（免疫致命伤害之后）依次判定：777 → 九璇之力 → 水纹。
- 残存的翎之祝福在翎之祝福之前翻倍；翎羽祝福每回合开始按没提升时的属性重新判定（本回合有效）。
"""

from __future__ import annotations

from avalon_contracts.rules.effect import EffectDef

from .batch7 import _TAKEN_LOST

_DONE = "not hit.dodged and hit.damage > 0"


def _loss_steps(acc: str, layers: str, step: str) -> list[dict]:
    """掉血（%）累计到 acc，满 step 得 1 层（不设上限）并清零（与批次 7 的守根哨卫相同）。"""
    full = f"self.vars.{acc} >= {step}"
    return [
        {"action": "flag", "name": acc, "value": f"self.vars.{acc} + {_TAKEN_LOST}"},
        {"action": "flag", "name": layers, "value": f"self.vars.{layers} + 1", "if": full},
        {"action": "flag", "name": acc, "value": 0, "if": full},
    ]


# "获得（0.1*生命）攻击力"加在面板上，按基础生命算（和其他"获得（X*属性）"一样；2026-11-24 按图鉴修正）
QIANXING_YUHUO = EffectDef.model_validate({
    "id": "qianxing_yuhuo",
    "name": "千星狱火",
    "desc": "获得（{atk_hp_pct:coef}*生命）攻击力。每降低{loss_step}%生命值，造成的伤害提高{dmg_pct}%。当生命低于"
            "{low_pct}%时，额外造成一次（{true_def_pct:coef}*防御）真实伤害。",
    "params": {"atk_hp_pct": 10, "loss_step": 10, "dmg_pct": 2, "low_pct": 20, "true_def_pct": 100},
    "static": [{"stat": "atk", "op": "add", "value": "self.base.hp * atk_hp_pct // 100"}],
    "auras": [{"stat": "dmg_pct", "op": "add", "value": "self.vars.千星狱火 * dmg_pct"}],
    "triggers": [
        {"on": "compute_hit", "priority": 110,
         "if": "not hit.dodged and self.hp_now * 100 < low_pct * self.panel.hp", "do": [
             {"action": "set_hit", "part": "true", "value": "self.panel.defense * true_def_pct // 100"}]},
        {"on": "taking_hit", "priority": 41, "if": f"{_TAKEN_LOST} > 0",
         "do": _loss_steps("千星狱火累计", "千星狱火", "loss_step")},
    ],
})

WANGCHAO_ZHIHUI = EffectDef.model_validate({
    "id": "wangchao_zhihui",
    "name": "王朝之徽",
    "desc": "提升{hp_pct}%生命和防御。每次受到攻击提升{reduce_pct}%免伤，上限{max_stacks}层。",
    "params": {"hp_pct": 8, "reduce_pct": 2, "max_stacks": 5},
    "static": [{"stat": "hp", "op": "add_pct", "value": "hp_pct"},
               {"stat": "defense", "op": "add_pct", "value": "hp_pct"}],
    "auras": [{"stat": "dmg_reduce", "op": "add", "value": "self.vars.王朝之徽 * reduce_pct"}],
    "triggers": [{"on": "taking_hit", "priority": 30, "if": "hit.damage > 0", "do": [
        {"action": "flag", "name": "王朝之徽", "value": "min(max_stacks, self.vars.王朝之徽 + 1)"}]}],
})

# 开场减益只在前几回合生效；爬塔的后续战斗没有（旧版如此）
JINNU_LONGWEI = EffectDef.model_validate({
    "id": "jinnu_longwei",
    "name": "烬怒龙威",
    "desc": "提升{dmg_pct}%增伤，战斗开始时，降低目标{def_pct}%防御和{resist}法抗，持续{rounds}回合。",
    "params": {"dmg_pct": 10, "def_pct": 50, "resist": 40, "rounds": 2},
    "static": [{"stat": "dmg_pct", "op": "max", "value": "dmg_pct"}],
    "auras": [{"target": "foe", "stat": "defense", "op": "down_pct", "value": "def_pct",
               "if": "entry and round_no >= 1 and round_no <= rounds"},
              {"target": "foe", "stat": "magic_resist", "op": "down", "value": "resist",
               "if": "entry and round_no >= 1 and round_no <= rounds"}],
})

JINNU_LONGXUE = EffectDef.model_validate({
    "id": "jinnu_longxue",
    "name": "烬怒龙血",
    "desc": "每损失{loss_step}%生命，提升{dmg_pct}%增伤。",
    "params": {"loss_step": 10, "dmg_pct": 3},
    "auras": [{"stat": "dmg_pct", "op": "add", "value": "self.vars.烬怒龙血 * dmg_pct"}],
    "triggers": [{"on": "taking_hit", "priority": 40, "if": f"{_TAKEN_LOST} > 0",
                  "do": _loss_steps("烬怒龙血累计", "烬怒龙血", "loss_step")}],
})

# 再生：回合开始时恢复，持续回合在恢复后减 1
SHUIWEN = EffectDef.model_validate({
    "id": "shuiwen",
    "name": "水纹",
    "desc": "提升{hp_pct}%生命。受到伤害时{chance}%概率获得{rounds}回合再生，再生期间每回合恢复（{heal_def_pct:coef}*防御）"
            "生命。再生持续期间不会重复获得再生。",
    "params": {"hp_pct": 10, "chance": 60, "rounds": 3, "heal_def_pct": 15},
    "static": [{"stat": "hp", "op": "add_pct", "value": "hp_pct"}],
    "triggers": [
        {"on": "before_damage", "priority": 30, "if": "self.vars.水纹再生 == 0", "chance": "chance", "do": [
            {"action": "flag", "name": "水纹再生", "value": "rounds"}]},
        {"on": "round_start", "priority": 46, "if": "self.vars.水纹再生 > 0", "do": [
            {"action": "heal", "value": "self.panel.defense * heal_def_pct // 100", "if": "self.hp_now > 0"},
            {"action": "flag", "name": "水纹再生", "value": "self.vars.水纹再生 - 1"}]},
    ],
})

FENGWEN = EffectDef.model_validate({
    "id": "fengwen",
    "name": "风纹",
    "desc": "提升{dmg_pct}%增伤。攻击后额外施加风蚀，每层风蚀降低{def_pct}%防御和法抗，无叠加上限。",
    "params": {"dmg_pct": 8, "def_pct": 1},
    "static": [{"stat": "dmg_pct", "op": "max", "value": "dmg_pct"}],
    "auras": [{"target": "foe", "stat": "defense", "op": "down_pct", "value": "foe.stacks.风蚀 * def_pct"},
              {"target": "foe", "stat": "magic_resist", "op": "down_pct_each", "value": "foe.stacks.风蚀 * def_pct"}],
    "triggers": [{"on": "on_hit", "priority": 137, "if": _DONE, "do": [
        {"action": "stack", "name": "风蚀", "op": "add", "value": 1}]}],
})

TUWEN = EffectDef.model_validate({
    "id": "tuwen",
    "name": "土纹",
    "desc": "提升{def_pct}%防御。生命首次低于{low_pct}%时，获得{reduce}%免伤持续{rounds}回合。",
    "params": {"def_pct": 20, "low_pct": 40, "reduce": 15, "rounds": 3},
    "static": [{"stat": "defense", "op": "add_pct", "value": "def_pct"}],
    "triggers": [{"on": "damage_taken", "priority": 810, "once": "battle",
                  "if": "self.hp_now > 0 and self.hp_now * 100 < low_pct * self.panel.hp", "do": [
                      {"action": "modify_stat", "stat": "dmg_reduce", "op": "add", "value": "reduce",
                       "rounds": "rounds + 1"}]}],
})

# 暴击伤害只翻倍超出 100% 的部分；无视防御里精准武器给的部分不翻倍（与旧版一致）
_DOUBLE = [("hp", "生命", None), ("atk", "攻击", None), ("defense", "防御", None), ("agi", "敏捷", None),
           ("mp", "法力", None), ("crit", "暴击率", None),
           ("crit_dmg", "爆伤", "100 + max(0, self.panel.crit_dmg - 100) * 2"),
           ("dodge", "闪避率", None), ("penetration", "物理穿透", None),
           ("pen_pct", "无视防御", "(self.panel.pen_pct - self.panel.precision_pen_pct) * 2 + self.panel.precision_pen_pct"),
           ("ignore_magic_resist", "法术穿透", None), ("ignore_resist_pct", "无视法抗", None),
           ("dmg_pct", "增伤", None), ("dmg_reduce", "免伤", None)]
CANCUN_LINGZHI = EffectDef.model_validate({
    "id": "cancun_lingzhi_zhufu",
    "name": "残存的翎之祝福",
    "desc": "战斗开始时，随机一项属性翻倍",
    "triggers": [{"on": "battle_start", "priority": -1, "do": [{"action": "random", "choices": [
        {"label": f"{label}翻倍", "do": [
            {"action": "modify_stat", "scope": "panel", "stat": stat, "op": "set", "value": formula}
            if formula else {"action": "modify_stat", "scope": "panel", "stat": stat, "op": "mul", "value": 2}]}
        for stat, label, formula in _DOUBLE]}]}],
})

LINGYU_ZHUFU = EffectDef.model_validate({
    "id": "lingyu_zhufu",
    "name": "翎羽祝福",
    "desc": "回合开始时，攻击或者法力随机一项提升{pct}%。",
    "params": {"pct": 80},
    "triggers": [{"on": "round_start", "priority": 5, "do": [
        {"action": "flag", "name": "翎羽攻击", "value": "self.panel.atk", "if": "round_no == 1"},
        {"action": "flag", "name": "翎羽法力", "value": "self.panel.mp", "if": "round_no == 1"},
        {"action": "modify_stat", "scope": "panel", "stat": "atk", "op": "set", "value": "self.vars.翎羽攻击"},
        {"action": "modify_stat", "scope": "panel", "stat": "mp", "op": "set", "value": "self.vars.翎羽法力"},
        {"action": "random", "choices": [
            {"label": "攻击", "do": [{"action": "modify_stat", "scope": "panel", "stat": "atk", "op": "set",
                                     "value": "self.vars.翎羽攻击 * (100 + pct) // 100"}]},
            {"label": "法力", "do": [{"action": "modify_stat", "scope": "panel", "stat": "mp", "op": "set",
                                     "value": "self.vars.翎羽法力 * (100 + pct) // 100"}]},
        ]},
    ]}],
})

BATCH9 = [QIANXING_YUHUO, WANGCHAO_ZHIHUI, JINNU_LONGWEI, JINNU_LONGXUE, SHUIWEN, FENGWEN, TUWEN,
          CANCUN_LINGZHI, LINGYU_ZHUFU]
