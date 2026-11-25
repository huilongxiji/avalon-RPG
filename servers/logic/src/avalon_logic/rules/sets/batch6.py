"""M3 批次 6：追击与按攻击叠层（飞梭、棱彩舞步、棱镜炫光、元素洗礼、元素之心、千机令、沉沦、涤荡）。

和旧版一致的规则：
- 攻击命中后几种碎晶的施加顺序：棱彩舞步 → 破镜之路 → 吟游之歌 → 棱镜炫光。
- "每一段命中后"对多段攻击的每段、以及飞梭的每段追击都会触发；只该对普通攻击生效的效果写 not seg.chase。
- 飞梭的追击基数在熔火之怒、涤荡之后，天火九舞之前取（去掉主攻击的暴击）。
"""

from __future__ import annotations

from avalon_contracts.rules.effect import EffectDef

from .batch1 import _shield

_DONE = "not hit.dodged and hit.damage > 0"


def _shard(value: str = "1") -> dict:
    return {"action": "stack", "name": "碎晶", "op": "add", "value": value}


# 暴击降低的防御：终末第 8 回合那一击不算（旧版如此，见批次 2 的终末）
YUANSU_XILI = EffectDef.model_validate({
    "id": "yuansu_xili",
    "name": "元素洗礼",
    "desc": "获得（{atk_mp_pct:coef}*法力）攻击和（{agi_mp_pct:coef}*法力）敏捷。暴击后降低{def_down}点防御，"
            "可叠加{max_stacks}层。",
    "params": {"atk_mp_pct": 5, "agi_mp_pct": 8, "def_down": 2, "max_stacks": 4},
    # 按属性换算的加成：多个套装都有时叠加（2026-11-24 按图鉴修正；旧版只取最大的一个）
    "static": [{"stat": "atk", "op": "add", "value": "self.base.mp * atk_mp_pct // 100"},
               {"stat": "agi", "op": "add", "value": "self.base.mp * agi_mp_pct // 100"}],
    "auras": [{"target": "foe", "stat": "defense", "op": "down", "value": "foe.stacks.洗礼 * def_down"}],
    "triggers": [{"on": "dealt_damage", "priority": 3, "if": "dealt.attack and hit.crit", "do": [
        {"action": "stack", "name": "洗礼", "op": "set", "value": "min(max_stacks, foe.stacks.洗礼 + 1)"},
    ]}],
})

# 削抗：普通攻击、终末第 8 回合那一击、群星之子第 7 回合的真实伤害造成伤害后判定（旧版如此）；护盾存在时概率提升
YUANSU_ZHIXIN = EffectDef.model_validate({
    "id": "yuansu_zhixin",
    "name": "元素之心",
    "desc": "战斗开始时，获得（{shield_mp_pct:coef}*法力）护盾，造成伤害时{chance}%概率降低{shred_pct}%法抗，"
            "可叠加{max_stacks}层，护盾存在期间概率提升至{shield_chance}%。",
    "params": {"shield_mp_pct": 60, "chance": 50, "shred_pct": 3, "max_stacks": 3, "shield_chance": 100},
    "auras": [{"stat": "ignore_resist_pct", "op": "add", "value": "foe.stacks.削抗 * shred_pct"}],
    "triggers": [
        {"on": "battle_start", "priority": 5, "do": [_shield("开场护盾_法力", "shield_mp_pct")]},
        # 普通攻击按出手前有没有护盾判定（这次攻击中途才获得的护盾不算）
        {"on": "before_action", "priority": 0, "do": [{"action": "flag", "name": "出手前有护盾", "value": "self.shield > 0"}]},
        {"on": "dealt_damage", "priority": 2,
         "if": "(dealt.attack or dealt.by.zhongmo or dealt.by.qunxing_zhizi_2) and foe.stacks.削抗 < max_stacks",
         "chance": "shield_chance if (self.vars.出手前有护盾 if dealt.attack else self.shield > 0) else chance", "do": [
             {"action": "stack", "name": "削抗", "op": "add", "value": 1},
         ]},
    ],
})

QIANJI_LING = EffectDef.model_validate({
    "id": "qianji_ling",
    "name": "千机令",
    "desc": "造成伤害后在目标身上留下印记，可无限叠加。普攻对持有印记的目标造成伤害时，每层印记增伤"
            "（{mark_agi_pct:coef}*敏捷）%。",
    "params": {"mark_agi_pct": 5},
    "triggers": [{"on": "on_hit", "priority": 160, "if": "hit.damage > 0", "do": [
        {"action": "scale_hit", "value": "10000 + foe.stacks.千机印记 * self.panel.agi * mark_agi_pct",
         "base": 10000, "with_true": True, "at_least_1": True},
        {"action": "stack", "name": "千机印记", "op": "add", "value": 1},
    ]}],
})

# 印记只用于击杀后的掉率、经验、代币加成（M4 游戏业务里结算）；多段攻击每段单独判定
CHENLUN = EffectDef.model_validate({
    "id": "chenlun",
    "name": "沉沦",
    "desc": "每次攻击后有{mark_chance}%概率留下印记（可无限叠加），有{execute_chance}%概率斩杀目标，击杀目标时，"
            "每层印记增加{kill_bonus}%装备掉率，经验，代币。",
    "params": {"mark_chance": 50, "execute_chance": 1, "kill_bonus": 1},
    "triggers": [
        {"on": "after_attack", "priority": 5, "if": "not hit.dodged and not hit.multi", "chance": "mark_chance",
         "do": [{"action": "stack", "name": "沉沦印记", "op": "add", "value": 1}]},
        {"on": "after_attack", "priority": 6, "if": "not hit.dodged and not hit.multi and foe.hp_now > 0",
         "chance": "execute_chance", "do": [{"action": "execute", "label": "沉沦：斩杀"}]},
        {"on": "segment", "priority": 130, "if": "not seg.chase", "chance": "mark_chance",
         "do": [{"action": "stack", "name": "沉沦印记", "op": "add", "value": 1}]},
        {"on": "segment", "priority": 131, "if": "not seg.chase", "chance": "execute_chance",
         "do": [{"action": "flag", "name": "沉沦斩杀", "value": 1}]},
        {"on": "after_attack", "priority": 5, "if": "hit.multi and self.vars.沉沦斩杀", "do": [
            {"action": "flag", "name": "沉沦斩杀", "value": 0},
            {"action": "execute", "label": "沉沦：斩杀"},
        ]},
    ],
})

DIDANG_4 = EffectDef.model_validate({
    "id": "didang_4",
    "name": "涤荡·4件",
    "desc": "提升{crit_dmg}%暴击伤害。攻击后有{chance}%概率增伤{bonus_pct}%",
    "params": {"crit_dmg": 50, "chance": 50, "bonus_pct": 200},
    "static": [{"stat": "crit_dmg", "op": "add", "value": "crit_dmg"}],
    "triggers": [
        {"on": "on_hit", "priority": 1, "if": "hit.damage > hit.true_part and not hit.multi", "chance": "chance",
         "do": [{"action": "scale_hit", "value": "100 + bonus_pct"}]},
        {"on": "segment", "priority": 60, "if": "not seg.chase", "chance": "chance",
         "do": [{"action": "scale_hit", "value": "100 + bonus_pct"}]},
    ],
})

# 追击：主攻击暴击后触发；基数是去掉暴击的主攻击伤害（暴击伤害按面板 + 精准武器加成还原）；
# 每段追击判定暴击用面板暴击率和面板暴击伤害
_CHASE = {"action": "chase", "base": "self.vars.飞梭基数", "pct": "chase_pct", "decay": "decay",
          "crit_rate": "min(100, self.panel.crit)", "crit_dmg": "self.panel.crit_dmg", "counter": "飞梭次数"}
FEISUO = EffectDef.model_validate({
    "id": "feisuo",
    "name": "飞梭",
    "desc": "暴击后追加一次{chase_pct}%伤害，本回合内每触发一次，伤害下降{decay}%。（火痕层数*{fire_chance}）%概率"
            "额外触发1次追击。若本回合未触发追击则下回合获得{crit_bonus}%暴击率，不可叠加，触发追击后移除加成。",
    "params": {"chase_pct": 90, "decay": 10, "fire_chance": 10, "crit_bonus": 20},
    "auras": [{"stat": "crit", "op": "add", "value": "crit_bonus * self.vars.飞梭加成"}],
    "triggers": [
        {"on": "round_start", "priority": 15, "do": [
            {"action": "flag", "name": "飞梭加成", "value": 1, "if": "self.vars.飞梭次数 == 0"},
            {"action": "flag", "name": "飞梭次数", "value": 0},
        ]},
        {"on": "on_hit", "priority": 110, "if": "hit.crit and hit.damage > 0", "do": [
            {"action": "flag", "name": "飞梭基数",
             "value": "hit.true_part + max(1, (hit.damage - hit.true_part) * 100 "
                      "// (self.panel.crit_dmg + hit.precision_crit_dmg))"},
        ]},
        {"on": "on_hit", "priority": 170, "if": "hit.crit and hit.damage > 0", "do": [
            _CHASE,
            {"action": "flag", "name": "飞梭加成", "value": 0, "if": "last.count > 0"},
        ]},
        {"on": "on_hit", "priority": 171, "if": "hit.crit and hit.damage > 0 and foe.stacks.火痕 > 0",
         "chance": "min(100, foe.stacks.火痕 * fire_chance)", "do": [
             _CHASE,
             {"action": "flag", "name": "飞梭加成", "value": 0, "if": "last.count > 0"},
         ]},
    ],
})

# 舞步增益：每次追击后永久提升攻击和暴击伤害（旧版：普通攻击按面板攻击加成，追击按基础攻击加成）；
# 追击用面板暴击率，暴击伤害含已叠的增益
LINGCAI_WUBU_4 = EffectDef.model_validate({
    "id": "lingcai_wubu_4",
    "name": "棱彩舞步·4件",
    "desc": "每次攻击后施加{shards}层碎晶并有{chance}%概率进行追击并提升{atk_pct}%攻击和{crit_dmg}%暴击伤害，"
            "追击造成（{chase_atk_pct:coef}*攻击+{chase_agi_pct:coef}*敏捷）物理伤害并施加{shards}层碎晶",
    "params": {"shards": 1, "chance": 66, "atk_pct": 8, "crit_dmg": 16, "chase_atk_pct": 80, "chase_agi_pct": 100},
    "auras": [{"stat": "atk", "op": "add", "value": "self.panel.atk * self.vars.舞步 * atk_pct // 100"},
              {"stat": "crit_dmg", "op": "add", "value": "self.vars.舞步 * crit_dmg"}],
    "triggers": [
        {"on": "on_hit", "priority": 90, "if": "hit.damage > 0", "do": [_shard("shards")]},
        {"on": "after_attack", "priority": 20, "if": _DONE + " and foe.hp_now > 0", "chance": "chance", "do": [
            {"action": "damage", "kind": "physical", "label": "棱彩舞步：追击", "can_crit": True,
             "value": "(self.panel.atk + self.base.atk * self.vars.舞步 * atk_pct // 100) * chase_atk_pct // 100"
                      " + self.agi * chase_agi_pct // 100",
             "crit_rate": "min(100, self.panel.crit)", "crit_dmg": "self.panel.crit_dmg + self.vars.舞步 * crit_dmg"},
            {"action": "flag", "name": "舞步", "value": "self.vars.舞步 + 1"},
            _shard("shards"),
        ]},
    ],
})

# 开场一击在第 1 回合开始时结算（爬塔的后续战斗没有）；周期伤害单独结算、吃增伤
LINGJING_XUANGUANG_4 = EffectDef.model_validate({
    "id": "lingjing_xuanguang_4",
    "name": "棱镜炫光·4件",
    "desc": "战斗开始时，造成（{open_mp_pct:coef}*法力+{open_agi_pct:coef}*敏捷）法术伤害并施加{shards}层碎晶"
            "降低{agi_down}%敏捷，持续{debuff_rounds}回合。造成法术伤害后有{shard_chance}%概率施加{shards}层碎晶。"
            "每{cycle_rounds}回合，额外造成（{cycle_mp_pct:coef}*法力*碎晶层数）法术伤害",
    "params": {"open_mp_pct": 100, "open_agi_pct": 40, "shards": 1, "agi_down": 20, "debuff_rounds": 7,
               "shard_chance": 88, "cycle_rounds": 3, "cycle_mp_pct": 12},
    "triggers": [
        {"on": "battle_start", "do": [
            {"action": "modify_stat", "target": "foe", "stat": "agi", "op": "down_pct", "value": "agi_down",
             "rounds": "debuff_rounds"},
        ]},
        {"on": "round_start", "priority": 12, "if": "entry and round_no == 1", "do": [
            {"action": "damage", "kind": "magic", "label": "棱镜炫光",
             "value": "(self.mp * open_mp_pct + self.panel.agi * open_agi_pct) // 100"},
            _shard("shards"),
        ]},
        {"on": "on_hit", "priority": 6, "if": "round_no % cycle_rounds == 0 and foe.stacks.碎晶 > 0", "do": [
            {"action": "damage", "kind": "magic", "label": "棱镜炫光：周期", "bonus": True,
             "value": "self.panel.mp * cycle_mp_pct * foe.stacks.碎晶 // 100"},
        ]},
        {"on": "on_hit", "priority": 105, "if": "hit.damage > 0 and weapon.magic", "chance": "shard_chance",
         "do": [_shard("shards")]},
    ],
})

BATCH6 = [YUANSU_XILI, YUANSU_ZHIXIN, QIANJI_LING, CHENLUN, DIDANG_4, FEISUO, LINGCAI_WUBU_4, LINGJING_XUANGUANG_4]
