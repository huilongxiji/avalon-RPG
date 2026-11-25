"""M3 批次 4：受到致命伤害时免疫的效果（幻身、吟游之语、遗梦、精灵祝福）。

和旧版一致的规则：
- 几个效果都能免疫时只有一个生效，按优先级：幻身 → 吟游之语 → 遗梦 → 精灵祝福
  （以后改写的天鸣守望排在最前面）。
- 幻身、遗梦每场战斗各一次；爬塔的后续战斗重新计算。
- 精灵祝福的法力加成"战斗开始时"获得，所以爬塔的后续战斗没有加成，也不能免疫。
"""

from __future__ import annotations

from avalon_contracts.rules.effect import EffectDef

HUANSHEN = EffectDef.model_validate({
    "id": "huanshen",
    "name": "幻身",
    "desc": "首次受到致命伤害时，免疫该伤害。",
    "triggers": [{"on": "fatal", "priority": 10, "once": "battle", "do": [
        {"action": "prevent"},
        {"action": "note", "text": "幻身：免疫致命伤害"},
    ]}],
})

# 再生：第 3 回合开始获得，持续 4 回合（第 3~6 回合每回合开始时恢复生命）；再生期间受到致命伤害就移除再生并免疫。
YINYOU_ZHIYU = EffectDef.model_validate({
    "id": "yinyou_zhiyu",
    "name": "吟游之语",
    "desc": "第{regen_round}回合开始时获得再生并额外造成（{regen_magic_mp_pct:coef}*法力）法术伤害，每回合恢复"
            "（{regen_mp_pct:coef}*法力）生命，持续{regen_rounds}回合。再生持续期间若受到致命伤害，则移除再生并免疫该伤害。"
            "第{late_round}回合开始造成（{late_magic_mp_pct:coef}*法力）法术伤害并施加{late_shards}层碎晶。",
    "params": {"regen_round": 3, "regen_magic_mp_pct": 70, "regen_mp_pct": 7, "regen_rounds": 4,
               "late_round": 7, "late_magic_mp_pct": 70, "late_shards": 3},
    "triggers": [
        {"on": "round_start", "priority": 45, "do": [
            {"action": "flag", "name": "吟游再生", "value": "regen_rounds", "if": "round_no == regen_round"},
            {"action": "heal", "value": "self.mp * regen_mp_pct // 100", "if": "self.vars.吟游再生 > 0"},
        ]},
        {"on": "round_start", "priority": 50, "if": "round_no == regen_round", "do": [
            {"action": "damage", "kind": "magic", "value": "self.mp * regen_magic_mp_pct // 100",
             "label": "吟游之语"},
        ]},
        {"on": "round_start", "priority": 80, "if": "round_no == late_round", "do": [
            {"action": "damage", "kind": "magic", "value": "self.mp * late_magic_mp_pct // 100",
             "label": "吟游之语"},
            {"action": "stack", "name": "碎晶", "op": "add", "value": "late_shards"},
        ]},
        {"on": "round_end", "if": "self.vars.吟游再生 > 0", "do": [
            {"action": "flag", "name": "吟游再生", "value": "self.vars.吟游再生 - 1"},
        ]},
        {"on": "fatal", "priority": 20, "if": "self.vars.吟游再生 > 0", "do": [
            {"action": "prevent"},
            {"action": "flag", "name": "吟游再生", "value": 0},
            {"action": "note", "text": "吟游之语：移除再生，免疫致命伤害"},
        ]},
    ],
})

# 旧版的"持续2回合"按对方的攻击次数算：免疫之后对方接下来的 2 次攻击都加闪避（对方每回合攻击一次）。
YIMENG = EffectDef.model_validate({
    "id": "yimeng",
    "name": "遗梦",
    "desc": "受到致命伤害时，免疫该次伤害，并获得{dodge}%闪避率，持续{hits}回合。",
    "params": {"dodge": 20, "hits": 2},
    "auras": [{"stat": "dodge", "op": "add", "value": "dodge if self.vars.遗梦闪避 > 0 else 0"}],
    "triggers": [
        {"on": "fatal", "priority": 30, "once": "battle", "do": [
            {"action": "prevent"},
            {"action": "flag", "name": "遗梦闪避", "value": "hits"},
            {"action": "flag", "name": "遗梦刚触发", "value": 1},
            {"action": "note", "text": "遗梦：免疫致命伤害"},
        ]},
        # 每次被攻击后少一次（触发免疫的那次攻击不算）
        {"on": "damage_taken", "priority": 10, "do": [
            {"action": "flag", "name": "遗梦闪避", "value": "self.vars.遗梦闪避 - 1",
             "if": "self.vars.遗梦刚触发 == 0 and self.vars.遗梦闪避 > 0"},
            {"action": "flag", "name": "遗梦刚触发", "value": 0},
        ]},
    ],
})

# "每次造成伤害后降低"只算普通攻击（2026-11-23 决定）。旧版还会在终末第 8 回合那一击后降低。
JINGLING_ZHUFU = EffectDef.model_validate({
    "id": "jingling_zhufu",
    "name": "精灵祝福",
    "desc": "战斗开始时获得{mp_pct}%法力加成，每次造成伤害后降低{decay}%加成，该加成存在期间受到致死伤害，"
            "移除全部加成免疫该次伤害。",
    "params": {"mp_pct": 12, "decay": 1},
    "auras": [{"stat": "mp", "op": "add", "value": "self.base.mp * self.vars.精灵祝福 // 100"}],
    "triggers": [
        {"on": "battle_start", "do": [{"action": "flag", "name": "精灵祝福", "value": "mp_pct"}]},
        {"on": "dealt_damage", "priority": 1,
         "if": "self.vars.精灵祝福 > 0 and dealt.attack", "do": [
             {"action": "flag", "name": "精灵祝福", "value": "max(0, self.vars.精灵祝福 - decay)"},
         ]},
        {"on": "fatal", "priority": 40, "if": "self.vars.精灵祝福 > 0", "do": [
            {"action": "prevent"},
            {"action": "flag", "name": "精灵祝福", "value": 0},
            {"action": "note", "text": "精灵祝福：移除加成，免疫致命伤害"},
        ]},
    ],
})

BATCH4 = [HUANSHEN, YINYOU_ZHIYU, YIMENG, JINGLING_ZHUFU]
