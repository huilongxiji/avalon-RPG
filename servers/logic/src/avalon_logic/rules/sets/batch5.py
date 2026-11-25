"""M3 批次 5：火痕一族（余烬王朝、浴火、火纹焚天、熔火之怒、天火九舞、天鸣守望、幻象纹路、阳炎庇护）。

火痕本身的规则在全局机制"火痕"里（目标每次攻击后按层数灼烧）；层数上限默认 7，
施加者的"火痕上限"属性大于 0 时用它（天火九舞 9 层、阳炎庇护 15 层）。世界BOSS免疫火痕。

和旧版一致的规则：
- 换掉普通攻击的套装在攻击命中（伤害大于 0）后先施加火痕，之后的效果按新的层数计算。
- 熔火之怒、天火九舞的"伤害提升至X%"在增伤之后、对这次攻击的非真实伤害生效；
  天火九舞对多段攻击每段单独判定，一次攻击最多叠 1 层火痕。
- 天鸣守望的起爆每场一次（起爆时火痕仍满层就不再起爆），在下个回合自己出手时结算。
"""

from __future__ import annotations

from avalon_contracts.rules.effect import EffectDef

_FIRE_PRIORITY = 70          # 物理攻击（余烬王朝、浴火）；法术攻击（火纹焚天）用 60，见批次 3
_GAIN_DONE = "not hit.dodged and hit.damage > 0"


def _gain(value: str = "fire") -> dict:
    return {"action": "stack", "name": "火痕", "op": "add", "value": value}


# 按图鉴修正（2026-11-23）："获得（0.2*攻击）敏捷"旧版从没加到属性上，新版生效。
YUJIN_WANGCHAO_4 = EffectDef.model_validate({
    "id": "yujin_wangchao_4",
    "name": "余烬王朝·4件",
    "desc": "获得（{agi_atk_pct:coef}*攻击）敏捷，攻击造成（{atk_pct:coef}*攻击+{hp_pct:coef}生命）物理伤害"
            "并施加{fire}层火痕",
    "params": {"agi_atk_pct": 20, "atk_pct": 110, "hp_pct": 30, "fire": 1},
    "static": [{"stat": "agi", "op": "add", "value": "self.base.atk * agi_atk_pct // 100"}],
    "triggers": [
        {"on": "attack", "priority": _FIRE_PRIORITY, "do": [
            {"action": "replace_hit", "hits": [
                {"kind": "physical", "value": "self.panel.atk * atk_pct // 100 + self.panel.hp * hp_pct // 100"}]},
        ]},
        {"on": "compute_hit", "priority": 10, "if": _GAIN_DONE, "do": [_gain()]},
    ],
})

YUHUO = EffectDef.model_validate({
    "id": "yuhuo",
    "name": "浴火",
    "desc": "攻击造成（{atk_pct:coef}*攻击+{hp_pct:coef}*生命*火痕层数）物理伤害并施加{fire}层火痕，"
            "生命首次低于{low_pct}%时造成（{burst_hp_pct:coef}*生命*火痕层数）物理伤害。",
    "params": {"atk_pct": 85, "hp_pct": 6, "fire": 1, "low_pct": 20, "burst_hp_pct": 20},
    "triggers": [
        {"on": "attack", "priority": _FIRE_PRIORITY, "do": [
            {"action": "replace_hit", "hits": [
                {"kind": "physical",
                 "value": "self.panel.atk * atk_pct // 100 + self.panel.hp * hp_pct * foe.stacks.火痕 // 100"}]},
        ]},
        {"on": "compute_hit", "priority": 10, "if": _GAIN_DONE, "do": [_gain()]},
        # 燃爆：按当前生命计算，不吃穿透和增伤，和这次攻击一起结算
        {"on": "on_hit", "priority": 150, "once": "battle",
         "if": "self.hp_now * 100 < low_pct * self.panel.hp", "do": [
             {"action": "damage", "kind": "physical", "label": "燃爆",
              "value": "self.hp_now * foe.stacks.火痕 * burst_hp_pct // 100"},
         ]},
    ],
})

HUOWEN_FENTIAN_4 = EffectDef.model_validate({
    "id": "huowen_fentian_4",
    "name": "火纹焚天·4件",
    "desc": "攻击造成（{mp_pct:coef}*法力）法术伤害并施加{fire}层火痕，每{cycle_rounds}回合额外造成"
            "（{cycle_mp_pct:coef}*法力*火痕层数）法术伤害并获得（{shield_mp_pct:coef}*法力*火痕层数）护盾",
    "params": {"mp_pct": 118, "fire": 1, "cycle_rounds": 3, "cycle_mp_pct": 16, "shield_mp_pct": 10},
    "triggers": [
        {"on": "attack", "priority": 60, "do": [
            {"action": "replace_hit", "hits": [{"kind": "magic", "value": "self.panel.mp * mp_pct // 100"}]},
        ]},
        {"on": "compute_hit", "priority": 10, "if": _GAIN_DONE, "do": [_gain()]},
        {"on": "compute_hit", "priority": 20,
         "if": "round_no % cycle_rounds == 0 and not hit.dodged and foe.stacks.火痕 > 0", "do": [
             {"action": "set_hit", "part": "magic", "value": "self.panel.mp * cycle_mp_pct * foe.stacks.火痕 // 100"},
         ]},
        {"on": "after_attack",
         "if": "round_no % cycle_rounds == 0 and not hit.dodged and hit.damage > 0 and foe.stacks.火痕 > 0", "do": [
             {"action": "shield", "value": "self.panel.mp * shield_mp_pct * foe.stacks.火痕 // 100"},
         ]},
    ],
})

RONGHUO_ZHINU_4 = EffectDef.model_validate({
    "id": "ronghuo_zhinu_4",
    "name": "熔火之怒·4件",
    "desc": "提升{crit_dmg}%暴击伤害和{pen}物理穿透，攻击{chance}%概率伤害提升至{mult}%并施加一层火痕。"
            "每层火痕增加{per_stack}%触发概率",
    "params": {"crit_dmg": 60, "pen": 40, "chance": 70, "mult": 210, "per_stack": 3},
    "static": [{"stat": "crit_dmg", "op": "add", "value": "crit_dmg"},
               {"stat": "penetration", "op": "add", "value": "pen"}],
    "triggers": [
        {"on": "on_hit", "priority": 20, "if": "hit.damage > 0",
         "chance": "min(100, chance + per_stack * foe.stacks.火痕)", "do": [
            {"action": "scale_hit", "value": "mult"},
            _gain("1"),
        ]},
    ],
})

TIANHUO_JIUWU = EffectDef.model_validate({
    "id": "tianhuo_jiuwu",
    "name": "天火九舞",
    "desc": "每次攻击{chance}%概率伤害提升至{mult}%并施加{fire}层火痕。火痕上限提升至{cap}层。",
    "params": {"chance": 60, "mult": 120, "fire": 1, "cap": 9},
    "static": [{"stat": "fire_cap", "op": "max", "value": "cap"}],
    "triggers": [
        {"on": "on_hit", "priority": 120, "if": "hit.damage > 0 and not hit.multi", "chance": "chance", "do": [
            {"action": "scale_hit", "value": "mult"},
            _gain(),
        ]},
        # 多段攻击：每段单独判定，一次攻击最多叠一层火痕
        {"on": "attack", "priority": 1, "do": [{"action": "flag", "name": "天火已叠", "value": 0}]},
        {"on": "segment", "priority": 120, "chance": "chance", "do": [
            {"action": "scale_hit", "value": "mult"},
            # 飞梭的追击段只提升伤害、不施加火痕
            {**_gain(), "if": "not seg.chase and self.vars.天火已叠 == 0"},
            {"action": "flag", "name": "天火已叠", "value": 1, "if": "not seg.chase"},
        ]},
    ],
})

TIANMING_SHOUWANG = EffectDef.model_validate({
    "id": "tianming_shouwang",
    "name": "天鸣守望",
    "desc": "造成法术伤害后{chance}%概率施加火痕，火痕层数首次达到{blast_stacks}层时，在下个回合开始时造成"
            "（{blast_mp_pct:coef}*法力）法术伤害。",
    "params": {"chance": 80, "blast_stacks": 7, "blast_mp_pct": 150},
    "triggers": [
        {"on": "on_hit", "priority": 130, "if": "hit.damage > 0 and weapon.magic", "chance": "chance",
         "do": [_gain("1")]},
        {"on": "on_hit", "priority": 131,
         "if": "hit.damage > 0 and not self.vars.天鸣待爆 and not self.vars.天鸣已爆 "
               "and foe.stacks.火痕 >= blast_stacks", "do": [
             {"action": "flag", "name": "天鸣待爆", "value": 1},
         ]},
        # 旧版的"下个回合开始时"实际在下个回合自己出手时（攻击之前）结算：对方先手时在对方攻击之后
        {"on": "attack", "priority": 0, "if": "self.vars.天鸣待爆 and foe.hp_now > 0", "do": [
            {"action": "flag", "name": "天鸣待爆", "value": 0},
            {"action": "flag", "name": "天鸣已爆", "value": "foe.stacks.火痕 >= blast_stacks"},
            {"action": "damage", "kind": "magic", "value": "self.panel.mp * blast_mp_pct // 100", "label": "天鸣守望"},
        ]},
    ],
})

HUANXIANG_WENLU = EffectDef.model_validate({
    "id": "huanxiang_wenlu",
    "name": "幻象纹路",
    "desc": "受到的攻击时降低（{reduce_mp_pct:coef}*法力+{reduce_stack_mp_pct:coef}*法力*火痕层数）伤害。"
            "每{cycle_rounds}回合额外造成（{cycle_mp_pct:coef}*法力）法术伤害并施加{fire}层火痕。",
    "params": {"reduce_mp_pct": 2, "reduce_stack_mp_pct": 2, "cycle_rounds": 3, "cycle_mp_pct": 90, "fire": 1},
    "triggers": [
        {"on": "taking_hit", "priority": 10, "if": "hit.damage > 0", "do": [
            {"action": "reduce_hit",
             "value": "self.panel.mp * (reduce_mp_pct + reduce_stack_mp_pct * foe.stacks.火痕) // 100"},
        ]},
        # 幻象灼烧：单独结算（吃增伤，不并入这次攻击、不吃攻击触发的伤害提升）
        {"on": "on_hit", "priority": 5, "if": "round_no % cycle_rounds == 0", "do": [
            {"action": "damage", "kind": "magic", "value": "self.panel.mp * cycle_mp_pct // 100", "bonus": True,
             "label": "幻象灼烧"},
            _gain(),
        ]},
    ],
})

# 免伤持续 N 回合：在受到攻击的这个回合触发，回合末开始计数，所以写 N+1（与旧版一致）
YANGYAN_BIHU = EffectDef.model_validate({
    "id": "yangyan_bihu",
    "name": "阳炎庇护",
    "desc": "每次受到伤害有{chance}%概率施加{fire}层火痕。生命首次低于{low_pct}%时，获得"
            "（{reduce_base}+{reduce_per_stack}*火痕层数）%免伤并恢复（{heal_atk_pct:coef}*攻击*火痕层数）生命，"
            "持续{rounds}回合。火痕上限提升至{cap}层。",
    "params": {"chance": 50, "fire": 1, "low_pct": 30, "reduce_base": 20, "reduce_per_stack": 2,
               "heal_atk_pct": 10, "rounds": 3, "cap": 15},
    "static": [{"stat": "fire_cap", "op": "max", "value": "cap"}],
    "triggers": [
        {"on": "taking_hit", "priority": 20, "if": "hit.damage > 0", "chance": "chance", "do": [_gain()]},
        {"on": "damage_taken", "priority": 800, "once": "battle",
         "if": "self.hp_now > 0 and self.hp_now * 100 < low_pct * self.panel.hp", "do": [
             {"action": "modify_stat", "stat": "dmg_reduce", "op": "add", "rounds": "rounds + 1",
              "value": "min(100, reduce_base + reduce_per_stack * foe.stacks.火痕)"},
             {"action": "heal", "value": "self.panel.atk * heal_atk_pct * foe.stacks.火痕 // 100"},
         ]},
    ],
})

BATCH5 = [YUJIN_WANGCHAO_4, YUHUO, HUOWEN_FENTIAN_4, RONGHUO_ZHINU_4, TIANHUO_JIUWU, TIANMING_SHOUWANG,
          HUANXIANG_WENLU, YANGYAN_BIHU]
