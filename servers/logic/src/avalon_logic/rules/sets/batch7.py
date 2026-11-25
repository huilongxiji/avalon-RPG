"""M3 批次 7：世界树一族（守根哨卫、腐心咏叹、世界树庇护、穿根、世界树赐福、守根、腐朽低语）。

和旧版一致的规则：
- "每降低10%生命"：每次掉血按（掉血量 × 100 ÷ 最大生命）取整累计，累计到一档就得 1 层并清零
  （一次跨过好几档也只得 1 层，多出的部分不结转）。腐心咏叹攻击时的自扣血也计入它自己的档位。
- 换掉普通攻击的先后：多段 → 法术（溺梦渊心、火纹焚天）→ 物理（余烬王朝、浴火）→ 腐心咏叹 → 世界树赐福。
- 攻击命中后这几种叠层的先后：守根 → 穿根（根蚀）→ 腐朽低语（腐朽）。
- 腐朽"受到的法术伤害提升"作用于全部法术伤害（2026-11-24 按图鉴修正；旧版火痕灼烧、天鸣守望起爆、
  吟游之语第 3/7 回合、终末第 8 回合那一击不吃）。
"""

from __future__ import annotations

from avalon_contracts.rules.effect import EffectDef

from .batch1 import _shield

_DONE = "not hit.dodged and hit.damage > 0"
_ROT_PRIORITY = 80          # 腐心咏叹的法术攻击
_BLESS_PRIORITY = 85        # 世界树赐福的法术攻击


def _loss_steps(acc: str, layers: str, lost: str, step: str, max_layers: str) -> list[dict]:
    """掉血 lost（%）累计到 acc，满 step 得 1 层（上限 max_layers）并清零。"""
    full = f"self.vars.{acc} >= {step}"
    return [
        {"action": "flag", "name": acc, "value": f"self.vars.{acc} + {lost}"},
        {"action": "flag", "name": layers, "value": f"min({max_layers}, self.vars.{layers} + 1)", "if": full},
        {"action": "flag", "name": acc, "value": 0, "if": full},
    ]


_TAKEN_LOST = "hit.damage * 100 // self.panel.hp"

SHOUGEN_SHAOWEI_4 = EffectDef.model_validate({
    "id": "shougen_shaowei_4",
    "name": "守根哨卫·4件",
    "desc": "每降低{loss_step}%生命获得{reduce_pct}%免伤。可叠加{max_stacks}层",
    "params": {"loss_step": 10, "reduce_pct": 3, "max_stacks": 9},
    "auras": [{"stat": "dmg_reduce", "op": "add", "value": "self.vars.守根哨卫 * reduce_pct"}],
    "triggers": [{"on": "taking_hit", "priority": 42, "if": f"{_TAKEN_LOST} > 0",
                  "do": _loss_steps("守根哨卫累计", "守根哨卫", _TAKEN_LOST, "loss_step", "max_stacks")}],
})

_ROT_COST = "max(1, self.panel.hp * cost_pct // 100)"
_ROT_LOST = f"{_ROT_COST} * 100 // self.panel.hp"
FUXIN_YONGTAN_4 = EffectDef.model_validate({
    "id": "fuxin_yongtan_4",
    "name": "腐心咏叹·4件",
    "desc": "攻击造成（{mp_pct:coef}*法力）法术伤害并减少自身{cost_pct}%生命。每降低{loss_step}%生命获得"
            "{dmg_pct}%增伤，可叠加{max_stacks}层",
    "params": {"mp_pct": 110, "cost_pct": 1, "loss_step": 10, "dmg_pct": 5, "max_stacks": 5},
    "auras": [{"stat": "dmg_pct", "op": "add", "value": "self.vars.腐心咏叹 * dmg_pct"}],
    "triggers": [
        {"on": "attack", "priority": _ROT_PRIORITY, "do": [
            {"action": "replace_hit", "hits": [{"kind": "magic", "value": "self.panel.mp * mp_pct // 100"}]},
        ]},
        # 自扣血在算完这次攻击之后、增伤之前（这次攻击就吃到新的一层增伤）
        {"on": "compute_hit", "priority": 900, "do": [
            {"action": "lose_hp", "value": _ROT_COST},
            *[dict(a, **{"if": f"{_ROT_LOST} > 0 and {a['if']}"}) if "if" in a else a
              for a in _loss_steps("腐心咏叹累计", "腐心咏叹", _ROT_LOST, "loss_step", "max_stacks")],
        ]},
        {"on": "taking_hit", "priority": 43, "if": f"{_TAKEN_LOST} > 0",
         "do": _loss_steps("腐心咏叹累计", "腐心咏叹", _TAKEN_LOST, "loss_step", "max_stacks")},
    ],
})

SHIJIESHU_BIHU_4 = EffectDef.model_validate({
    "id": "shijieshu_bihu_4",
    "name": "世界树庇护·4件",
    "desc": "战斗开始时获得（{shield_mp_pct:coef}法力）护盾；每回合恢复（{heal_hp_pct:coef}生命+{heal_mp_pct:coef}法力）生命",
    "params": {"shield_mp_pct": 100, "heal_hp_pct": 1, "heal_mp_pct": 7},
    "triggers": [
        {"on": "battle_start", "priority": 5, "do": [_shield("开场护盾_法力", "shield_mp_pct")]},
        {"on": "round_start", "priority": 42, "do": [
            {"action": "heal", "value": "(self.panel.hp * heal_hp_pct + self.mp * heal_mp_pct) // 100"},
        ]},
    ],
})

CHUANGEN = EffectDef.model_validate({
    "id": "chuangen",
    "name": "穿根",
    "desc": "获得（{pen_agi_pct:coef}*敏捷）物理穿透。攻击后有{chance}%概率施加1层根蚀，每层根蚀使目标受到暴击伤害"
            "提升{crit_dmg_pct}%，上限{max_stacks}层。",
    "params": {"pen_agi_pct": 40, "chance": 60, "crit_dmg_pct": 15, "max_stacks": 4},
    "auras": [{"stat": "penetration", "op": "add", "value": "self.panel.agi * pen_agi_pct // 100"},
              {"stat": "crit_dmg", "op": "add", "value": "foe.stacks.根蚀 * crit_dmg_pct"}],
    "triggers": [{"on": "on_hit", "priority": 136, "if": _DONE, "chance": "chance", "do": [
        {"action": "stack", "name": "根蚀", "op": "set", "value": "min(max_stacks, foe.stacks.根蚀 + 1)"},
    ]}],
})

SHIJIESHU_CIFU = EffectDef.model_validate({
    "id": "shijieshu_cifu",
    "name": "世界树赐福",
    "desc": "战斗开始时，获得（{agi_mp_pct:coef}*法力）敏捷。攻击造成（{mp_pct:coef}*法力）法术伤害并获得"
            "（{shield_mp_pct:coef}*法力）护盾。",
    "params": {"agi_mp_pct": 10, "mp_pct": 105, "shield_mp_pct": 8},
    # 按属性换算的加成：多个套装都有时叠加（2026-11-24 按图鉴修正；旧版只取最大的一个）
    "static": [{"stat": "agi", "op": "add", "value": "self.base.mp * agi_mp_pct // 100"}],
    "triggers": [
        {"on": "attack", "priority": _BLESS_PRIORITY, "do": [
            {"action": "replace_hit", "hits": [{"kind": "magic", "value": "self.panel.mp * mp_pct // 100"}]},
        ]},
        {"on": "compute_hit", "priority": 5, "if": "hit.by.shijieshu_cifu and " + _DONE, "do": [
            {"action": "shield", "value": "self.mp * shield_mp_pct // 100"},
        ]},
    ],
})

SHOUGEN = EffectDef.model_validate({
    "id": "shougen",
    "name": "守根",
    "desc": "提升{crit_dmg}%暴击伤害。每次攻击后提升{crit_per}%暴击率，可叠加{max_stacks}层。",
    "params": {"crit_dmg": 30, "crit_per": 3, "max_stacks": 5},
    "static": [{"stat": "crit_dmg", "op": "add", "value": "crit_dmg"}],
    "auras": [{"stat": "crit", "op": "add", "value": "self.vars.守根 * crit_per"}],
    "triggers": [{"on": "on_hit", "priority": 135, "if": _DONE, "do": [
        {"action": "flag", "name": "守根", "value": "min(max_stacks, self.vars.守根 + 1)"},
    ]}],
})

# 周期伤害：没被闪避就结算，单独结算、吃增伤；结算后施加 1 层腐朽（不论伤害多少）。
# 腐朽对全部法术伤害生效。
FUXIU_DIYU = EffectDef.model_validate({
    "id": "fuxiu_diyu",
    "name": "腐朽低语",
    "desc": "每{cycle_rounds}回合造成（{cycle_mp_pct:coef}*法力）法术伤害并恢复实际伤害量的生命值，实际恢复生命值不超过"
            "（{heal_mp_pct:coef}*法力）。造成法术伤害后施加1层腐朽，每层腐朽使目标受到的法术伤害提升{shred_pct}%，"
            "上限{max_stacks}层。",
    "params": {"cycle_rounds": 3, "cycle_mp_pct": 50, "heal_mp_pct": 10, "shred_pct": 2, "max_stacks": 10},
    "auras": [{"target": "foe", "stat": "magic_taken_pct", "op": "add", "value": "foe.stacks.腐朽 * shred_pct"}],
    "triggers": [
        {"on": "on_hit", "priority": 7, "if": "round_no % cycle_rounds == 0", "do": [
            {"action": "damage", "kind": "magic", "label": "腐朽低语", "bonus": True,
             "value": "self.panel.mp * cycle_mp_pct // 100"},
            {"action": "heal", "value": "min(last.damage, self.panel.mp * heal_mp_pct // 100)"},
            {"action": "stack", "name": "腐朽", "op": "set", "value": "min(max_stacks, foe.stacks.腐朽 + 1)"},
        ]},
        {"on": "on_hit", "priority": 138, "if": _DONE + " and weapon.magic", "do": [
            {"action": "stack", "name": "腐朽", "op": "set", "value": "min(max_stacks, foe.stacks.腐朽 + 1)"},
        ]},
    ],
})

BATCH7 = [SHOUGEN_SHAOWEI_4, FUXIN_YONGTAN_4, SHIJIESHU_BIHU_4, CHUANGEN, SHIJIESHU_CIFU, SHOUGEN, FUXIU_DIYU]
