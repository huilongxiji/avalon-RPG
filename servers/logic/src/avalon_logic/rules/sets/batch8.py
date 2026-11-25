"""M3 批次 8：群星一族（群星之子·2件、苍星、777、幸运三角、九璇之力、侵星璇玑、万象星盘）。

和旧版一致的规则：
- 群星之子·2件按武器区分：星之子、千星狱火矛 / 星之语、千星熔烬弓 / 星之言、千星唤龙权（装备编号见下）。
- 星之言的法术攻击排在多段攻击之后、溺梦渊心等法术攻击之前。
- 受到攻击、扣血前（免疫致命伤害之后）依次判定：777 → 九璇之力。
- 幸运三角：出手时判定（天鸣守望起爆之后）；持续期间提升普通攻击的暴击率；无视防御、无视法抗和增伤作用于玩家造成的全部伤害
  （增伤不作用于真实伤害；2026-11-24 按图鉴修正，旧版只作用于普通攻击和几个单独结算的套装伤害）。
"""

from __future__ import annotations

from avalon_contracts.rules.effect import EffectDef

_DONE = "not hit.dodged and hit.damage > 0"

# 群星之子的武器（装备编号）
_STAR_CHILD = "(weapon.id == 138 or weapon.id == 181)"      # 星之子、千星狱火矛
_STAR_SONG = "(weapon.id == 139 or weapon.id == 182)"       # 星之语、千星熔烬弓
_STAR_WORD = "weapon.id == 140"                             # 星之言
_STAR_DRAGON = "weapon.id == 183"                           # 千星唤龙权
_STAR_MAGIC = f"({_STAR_WORD} or {_STAR_DRAGON})"
_STAR_PRIORITY = 55        # 星之言的法术攻击：多段攻击（50）之后、溺梦渊心等法术攻击（60）之前

QUNXING_ZHIZI_2 = EffectDef.model_validate({
    "id": "qunxing_zhizi_2",
    "name": "群星之子·2件",
    "desc": "根据武器种类提供对应套装效果",
    "params": {"reduce": 10, "def_pct": 40, "true_round": 7, "true_hp_pct": 20,
               "crit": 10, "hit1_atk_pct": 50, "hit1_agi_pct": 20, "hit2_atk_pct": 10, "hit2_agi_pct": 80,
               "dodge": 10, "ignore_resist_pct": 17, "word_mp_pct": 125, "dragon_mp_pct": 115,
               "star_max": 3, "star_reduce": 5},
    "static": [
        {"stat": "dmg_reduce", "op": "add", "value": "reduce", "if": _STAR_CHILD},
        {"stat": "crit", "op": "add", "value": "crit", "if": _STAR_SONG},
        {"stat": "dodge", "op": "add", "value": "dodge", "if": _STAR_MAGIC},
        {"stat": "ignore_resist_pct", "op": "max", "value": "ignore_resist_pct", "if": _STAR_MAGIC},
    ],
    # 星印：每层使目标造成的伤害降低（世界BOSS不受影响）
    "auras": [{"target": "foe", "stat": "atk", "op": "down_pct_each",
               "value": "min(100, foe.stacks.星印 * star_reduce) if not foe.is_world_boss else 0"}],
    "triggers": [
        # 星之子：攻击后额外造成（0.4*防御）物理伤害；第七回合开始时造成（0.2*生命）真实伤害
        {"on": "compute_hit", "if": f"{_STAR_CHILD} and not hit.dodged", "do": [
            {"action": "set_hit", "part": "physical", "value": "self.panel.defense * def_pct // 100"},
        ]},
        {"on": "round_start", "priority": 70, "if": f"{_STAR_CHILD} and round_no == true_round", "do": [
            {"action": "damage", "kind": "true", "label": "群星之子", "value": "self.panel.hp * true_hp_pct // 100"},
        ]},
        # 星之语：攻击变成二连击
        {"on": "attack", "priority": 50, "if": _STAR_SONG, "do": [
            {"action": "replace_hit", "hits": [
                {"kind": "physical", "value": "(self.panel.atk * hit1_atk_pct + self.panel.agi * hit1_agi_pct) // 100"},
                {"kind": "physical", "value": "(self.panel.atk * hit2_atk_pct + self.panel.agi * hit2_agi_pct) // 100"},
            ]},
        ]},
        # 星之言：攻击造成法术伤害并施加 1 层星印
        {"on": "attack", "priority": _STAR_PRIORITY, "if": _STAR_MAGIC, "do": [
            {"action": "replace_hit", "hits": [{"kind": "magic", "value":
                f"self.panel.mp * (word_mp_pct if {_STAR_WORD} else dragon_mp_pct) // 100"}]},
        ]},
        {"on": "compute_hit", "priority": 5, "if": f"hit.by.qunxing_zhizi_2 and {_STAR_MAGIC} and " + _DONE, "do": [
            {"action": "stack", "name": "星印", "op": "set", "value": "min(star_max, foe.stacks.星印 + 1)"},
        ]},
    ],
})

CANGXING = EffectDef.model_validate({
    "id": "cangxing",
    "name": "苍星",
    "desc": "每次攻击{heal_chance}%概率恢复（{heal_mp_pct:coef}*法力）生命，每{cycle_rounds}回合，攻击造成"
            "（{cycle_mp_pct:coef}*法力）法术伤害。",
    "params": {"heal_chance": 33, "heal_mp_pct": 9, "cycle_rounds": 3, "cycle_mp_pct": 132},
    "triggers": [
        {"on": "compute_hit", "priority": 15, "if": "round_no % cycle_rounds == 0 and not hit.dodged", "do": [
            {"action": "set_hit", "part": "magic", "value": "self.panel.mp * cycle_mp_pct // 100"},
        ]},
        # 造成伤害就判定（被闪避时只有真实伤害，也算）
        {"on": "on_hit", "priority": 141, "if": "hit.damage > 0", "chance": "heal_chance", "do": [
            {"action": "heal", "value": "self.panel.mp * heal_mp_pct // 100"},
        ]},
        {"on": "after_attack", "priority": 0, "if": "hit.dodged and hit.damage > 0", "chance": "heal_chance", "do": [
            {"action": "heal", "value": "self.panel.mp * heal_mp_pct // 100"},
        ]},
    ],
})

# 三种效果互斥：持续期间和冷却期间不再判定。「七七七」标记：1 防御、2 治疗、3 闪避
SEVEN = EffectDef.model_validate({
    "id": "qiqiqi",
    "name": "777",
    "desc": "受到伤害时有{def_chance}%概率提升{def_pct}%防御，有{heal_chance}%概率恢复（{heal_atk_pct:coef}*攻击+"
            "{heal_mp_pct:coef}*法力）生命，有{dodge_chance}%概率获得{dodge}%闪避率，持续{rounds}回合，冷却{cooldown}回合",
    "params": {"def_chance": 50, "def_pct": 15, "heal_chance": 45, "heal_atk_pct": 7, "heal_mp_pct": 7,
               "dodge_chance": 5, "dodge": 17, "rounds": 2, "cooldown": 3},
    "auras": [{"stat": "defense", "op": "mul_pct", "value": "def_pct if self.vars.七七七 == 1 else 0"},
              {"stat": "dodge", "op": "add", "value": "dodge if self.vars.七七七 == 3 else 0"}],
    "triggers": [
        {"on": "round_start", "priority": 16, "do": [
            {"action": "flag", "name": "七七七持续", "value": "self.vars.七七七持续 - 1", "if": "self.vars.七七七持续 > 0"},
            {"action": "flag", "name": "七七七", "value": 0, "if": "self.vars.七七七持续 == 0"},
            {"action": "flag", "name": "七七七冷却", "value": "self.vars.七七七冷却 - 1", "if": "self.vars.七七七冷却 > 0"},
        ]},
        {"on": "before_damage", "priority": 10, "if": "self.vars.七七七持续 == 0 and self.vars.七七七冷却 == 0", "do": [
            {"action": "random", "choices": [
                {"label": "防御", "weight": 50, "do": [{"action": "flag", "name": "七七七", "value": 1}]},
                {"label": "治疗", "weight": 45, "do": [
                    {"action": "flag", "name": "七七七", "value": 2},
                    {"action": "heal", "value": "(self.panel.atk * heal_atk_pct + self.panel.mp * heal_mp_pct) // 100"},
                ]},
                {"label": "闪避", "weight": 5, "do": [{"action": "flag", "name": "七七七", "value": 3}]},
            ]},
            {"action": "flag", "name": "七七七持续", "value": "rounds"},
            {"action": "flag", "name": "七七七冷却", "value": "cooldown"},
        ]},
    ],
})

_TRI_ON = "self.vars.三角持续 > 0"
_TRI_TICK = [
    {"action": "flag", "name": "三角冷却", "value": "self.vars.三角冷却 - 1",
     "if": "self.vars.三角持续 == 0 and self.vars.三角冷却 > 0"},
    {"action": "flag", "name": "三角持续", "value": "self.vars.三角持续 - 1", "if": _TRI_ON},
    {"action": "flag", "name": "三角冷却", "value": "cooldown", "if": "self.vars.三角持续 == 0 and self.vars.三角增伤 > 0"},
    {"action": "flag", "name": "三角增伤", "value": 0, "if": "self.vars.三角持续 == 0"},
]
LUCKY_TRIANGLE = EffectDef.model_validate({
    "id": "xingyun_sanjiao",
    "name": "幸运三角",
    "desc": "攻击时有{low_chance}%概率获得{low_pct}%增伤，有{mid_chance}%概率获得{mid_pct}%增伤，{high_chance}%概率获得"
            "{high_pct}%增伤，{crit}%暴击率，{ignore_def}%无视防御和{ignore_resist}%无视法抗，持续{rounds}回合，"
            "冷却{cooldown}回合。",
    "params": {"low_chance": 50, "low_pct": 7, "mid_chance": 45, "mid_pct": 14, "high_chance": 5, "high_pct": 17,
               "crit": 10, "ignore_def": 30, "ignore_resist": 50, "rounds": 3, "cooldown": 2},
    "auras": [{"stat": "extra_dmg_mul_pct", "op": "add", "value": "self.vars.三角增伤"},
              {"stat": "crit", "op": "add", "value": f"crit if {_TRI_ON} else 0"},
              {"stat": "extra_ignore_def_pct", "op": "add", "value": f"ignore_def if {_TRI_ON} else 0"},
              {"stat": "extra_ignore_resist_pct", "op": "add", "value": f"ignore_resist if {_TRI_ON} else 0"}],
    "triggers": [
        # 出手时判定（天鸣守望起爆之后、这次攻击读属性之前）
        {"on": "attack", "priority": 1, "if": "self.vars.三角持续 == 0 and self.vars.三角冷却 == 0", "do": [
            {"action": "random", "choices": [
                {"label": "增伤（小）", "weight": "low_chance", "do": [{"action": "flag", "name": "三角增伤", "value": "low_pct"}]},
                {"label": "增伤（中）", "weight": "mid_chance", "do": [{"action": "flag", "name": "三角增伤", "value": "mid_pct"}]},
                {"label": "增伤（大）", "weight": "high_chance", "do": [{"action": "flag", "name": "三角增伤", "value": "high_pct"}]},
            ]},
            {"action": "flag", "name": "三角持续", "value": "rounds"},
        ]},
        # 每次出手：持续回合减 1，结束时进入冷却；没有持续时冷却减 1。旧版在这次攻击结算的中途扣
        # （命中后：守根、苍星之后，浴火、千机令、飞梭追击之前；被闪避时在攻击结算后最先扣）
        {"on": "on_hit", "priority": 145, "do": _TRI_TICK},
        {"on": "after_attack", "priority": -1, "if": "hit.dodged", "do": _TRI_TICK},
    ],
})

JIUXUAN = EffectDef.model_validate({
    "id": "jiuxuan_zhili",
    "name": "九璇之力",
    "desc": "每次受到攻击{chance}%概率降低{reduce_pct}%伤害，并造成（{def_pct:coef}*防御）物理伤害",
    "params": {"chance": 60, "reduce_pct": 10, "def_pct": 50},
    "triggers": [{"on": "before_damage", "priority": 20, "chance": "chance", "do": [
        {"action": "reduce_hit", "value": "hit.damage - hit.damage * (100 - reduce_pct) // 100"},
        {"action": "damage", "kind": "physical", "label": "九璇之力", "base_def": True,
         "value": "self.panel.defense * def_pct // 100"},
    ]}],
})

QINXING = EffectDef.model_validate({
    "id": "qinxing_xuanji",
    "name": "侵星璇玑",
    "desc": "获得（{atk_agi_pct:coef}*敏捷）攻击。造成伤害后降低{atk_down}%攻击并降低{def_down}点防御，减防可无限叠加。",
    "params": {"atk_agi_pct": 10, "atk_down": 5, "def_down": 2},
    # 按属性换算的加成：多个套装都有时叠加（2026-11-24 按图鉴修正；旧版只取最大的一个）
    "static": [{"stat": "atk", "op": "add", "value": "self.base.agi * atk_agi_pct // 100"}],
    "auras": [{"target": "foe", "stat": "defense", "op": "down", "value": "foe.stacks.蚀甲 * def_down"},
              {"target": "foe", "stat": "atk", "op": "down_pct_each",
               "value": "atk_down if foe.stacks.蚀甲 > 0 and not foe.is_world_boss else 0"}],
    "triggers": [
        # 单段攻击：造成伤害就叠（被闪避时只有真实伤害，也算）；多段攻击每段命中叠一层
        {"on": "on_hit", "priority": 139, "if": "hit.damage > 0 and not hit.multi", "do": [
            {"action": "stack", "name": "蚀甲", "op": "add", "value": 1}]},
        {"on": "after_attack", "priority": 0, "if": "hit.dodged and hit.damage > 0 and not hit.multi", "do": [
            {"action": "stack", "name": "蚀甲", "op": "add", "value": 1}]},
        {"on": "segment", "priority": 140, "if": "not seg.chase", "do": [
            {"action": "stack", "name": "蚀甲", "op": "add", "value": 1}]},
    ],
})

WANXIANG = EffectDef.model_validate({
    "id": "wanxiang_xingpan",
    "name": "万象星盘",
    "desc": "获得（{agi_mp_pct:coef}*法力）敏捷，每次造成法术伤害降低目标{shred_pct}%法抗，可叠加{max_stacks}层。"
            "每{heal_rounds}回合恢复（{heal_mp_pct:coef}*法力）生命。",
    "params": {"agi_mp_pct": 15, "shred_pct": 1, "max_stacks": 7, "heal_rounds": 5, "heal_mp_pct": 25},
    "static": [{"stat": "agi", "op": "add", "value": "self.base.mp * agi_mp_pct // 100"}],
    "auras": [{"stat": "ignore_resist_pct", "op": "add", "value": "foe.stacks.星盘削抗 * shred_pct"}],
    "triggers": [
        {"on": "round_start", "priority": 41, "if": "round_no % heal_rounds == 0", "do": [
            {"action": "heal", "value": "self.panel.mp * heal_mp_pct // 100"}]},
        # 使用法术武器时，普通攻击（以及终末第 8 回合那一击、群星之子第 7 回合的真实伤害）造成伤害后
        {"on": "dealt_damage", "priority": 2,
         "if": "(dealt.attack or dealt.by.zhongmo or dealt.by.qunxing_zhizi_2) and weapon.magic"
               " and foe.stacks.星盘削抗 < max_stacks", "do": [
             {"action": "stack", "name": "星盘削抗", "op": "add", "value": 1}]},
    ],
})

BATCH8 = [QUNXING_ZHIZI_2, CANGXING, SEVEN, LUCKY_TRIANGLE, JIUXUAN, QINXING, WANXIANG]
