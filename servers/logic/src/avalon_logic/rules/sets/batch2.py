"""M3 批次 2：战斗开始和指定回合触发的效果、开场比较敏捷的效果，以及并入普通攻击结算的追加伤害。

几条和旧版一致的规则（写效果时要注意）：
- 爬塔的后续战斗不触发"战斗开始"，旧版也把这些"第 N 回合"效果一起关掉，所以按回合触发的都带 entry 条件。
- 追加到这次攻击里的物理/法术伤害（set_hit）沿用这次攻击的穿透，并入主攻击一起吃增伤；
  追加的真实伤害先加在一起，最后统一按免伤和等级结算一次。
- 千丝的清层放在最后（优先级 200，没写优先级的是 100）：同一次攻击里其他追加伤害用的是清层前的防御。
"""

from __future__ import annotations

from avalon_contracts.rules.effect import EffectDef

_NOT_DODGED = "not hit.dodged"


def _on_round(param: str) -> str:
    return f"entry and round_no == {param}"


ZHONGMO_SHIKE_4 = EffectDef.model_validate({
    "id": "zhongmo_shike_4",
    "name": "终末时刻·4件",
    "desc": "战斗开始，降低敌方{def_down}点防御和{resist_down}点法抗，持续{rounds}回合，第{true_round}回合造成"
            "（{true_atk_pct:coef}*攻击+{true_mp_pct:coef}*法力）的真实伤害",
    "params": {"def_down": 7, "resist_down": 3, "rounds": 5, "true_round": 6, "true_atk_pct": 30, "true_mp_pct": 30},
    "triggers": [
        {"on": "battle_start", "do": [
            {"action": "modify_stat", "target": "foe", "stat": "defense", "op": "down", "value": "def_down",
             "rounds": "rounds"},
            # 旧版"降低法抗"是给自己加法术穿透（对固定法术穿透生效的地方都生效）
            {"action": "modify_stat", "stat": "ignore_magic_resist", "op": "add", "value": "resist_down",
             "rounds": "rounds"},
        ]},
        # 被闪避也会造成
        {"on": "compute_hit", "if": _on_round("true_round"), "do": [
            {"action": "set_hit", "part": "true",
             "value": "self.panel.atk * true_atk_pct // 100 + self.panel.mp * true_mp_pct // 100"},
        ]},
    ],
})

# 附加伤害：多个套装都有时叠加（2026-11-23 决定；旧版只取最大的一个）
ZHAOZE = EffectDef.model_validate({
    "id": "zhaoze",
    "name": "沼泽套装",
    "desc": "提升{reduce}%免伤，攻击额外造成（{hp_permille:permille}*生命值）物理伤害",
    "params": {"reduce": 5, "hp_permille": 30},
    "static": [{"stat": "dmg_reduce", "op": "add", "value": "reduce"}],
    "triggers": [{"on": "compute_hit", "if": _NOT_DODGED, "do": [
        {"action": "set_hit", "part": "physical", "value": "self.panel.hp * hp_permille // 1000"},
    ]}],
})

GUSHU_ZHIXIN = EffectDef.model_validate({
    "id": "gushu_zhixin",
    "name": "古树之心",
    "desc": "提升{pen}法术穿透。第{heal_round:cn}回合开始时治疗（{heal_mp_pct:coef}*法力）的生命值。",
    "params": {"pen": 10, "heal_round": 5, "heal_mp_pct": 30},
    "static": [{"stat": "ignore_magic_resist", "op": "add", "value": "pen"}],
    "triggers": [{"on": "round_start", "priority": 40, "if": _on_round("heal_round"), "do": [
        {"action": "heal", "value": "self.panel.mp * heal_mp_pct // 100"},
    ]}],
})

BEIMING_ZHIYING = EffectDef.model_validate({
    "id": "beiming_zhiying",
    "name": "悲鸣之影",
    "desc": "战斗开始时，若敏捷大于目标则获得{lead_agi_pct}%敏捷，若敏捷小于目标则每次普攻额外造成"
            "（{slow_true_agi_pct:coef}*敏捷）的真实伤害。",
    "params": {"lead_agi_pct": 10, "slow_true_agi_pct": 20},
    "triggers": [
        {"on": "battle_start", "if": "self.panel.agi > foe.panel.agi", "do": [
            {"action": "modify_stat", "stat": "agi", "op": "add_base_pct", "value": "lead_agi_pct"},
        ]},
        {"on": "compute_hit", "if": f"entry and {_NOT_DODGED} and self.panel.agi < foe.panel.agi", "do": [
            {"action": "set_hit", "part": "true", "value": "self.panel.agi * slow_true_agi_pct // 100"},
        ]},
    ],
})

NVYAO_BEIMING = EffectDef.model_validate({
    "id": "nvyao_beiming",
    "name": "女妖悲鸣",
    "desc": "战斗开始时，降低双方{def_down_pct}%防御力和{resist_down}点法抗，持续{rounds}回合。"
            "第{burst_round:cn}回合造成（{burst_atk_pct:coef}*攻击力）物理伤害或者（{burst_mp_pct:coef}*法力）法术伤害，"
            "并降低{atk_down_pct}%攻击力，持续{atk_down_rounds}回合。",
    "params": {"def_down_pct": 10, "resist_down": 5, "rounds": 3, "burst_round": 4, "burst_atk_pct": 60,
               "burst_mp_pct": 80, "atk_down_pct": 10, "atk_down_rounds": 99},
    "triggers": [
        {"on": "battle_start", "do": [
            {"action": "modify_stat", "target": "foe", "stat": "defense", "op": "down_pct", "value": "def_down_pct",
             "rounds": "rounds"},
            {"action": "modify_stat", "stat": "defense", "op": "down_pct", "value": "def_down_pct",
             "rounds": "rounds"},
            {"action": "modify_stat", "stat": "ignore_magic_resist", "op": "add", "value": "resist_down",
             "rounds": "rounds"},
        ]},
        # 法力高于攻击时造成法术伤害，否则造成物理伤害（都用面板值比较）
        {"on": "compute_hit", "if": f"{_on_round('burst_round')} and {_NOT_DODGED}", "do": [
            {"action": "set_hit", "part": "magic", "value": "self.panel.mp * burst_mp_pct // 100",
             "if": "self.panel.mp > self.panel.atk"},
            {"action": "set_hit", "part": "physical", "value": "self.panel.atk * burst_atk_pct // 100",
             "if": "self.panel.mp <= self.panel.atk"},
        ]},
        # 降攻从下一回合开始算（不论这一回合是否打中）；世界BOSS不受影响
        {"on": "round_start", "if": "entry and round_no == burst_round + 1 and not foe.is_world_boss", "do": [
            {"action": "modify_stat", "target": "foe", "stat": "atk", "op": "down_pct", "value": "atk_down_pct",
             "rounds": "atk_down_rounds"},
        ]},
    ],
})

QIANSI_YIN = EffectDef.model_validate({
    "id": "qiansi_yin",
    "name": "千丝引",
    "desc": "攻击后降低敌方{def_down}防御，可叠加{max_stacks}层。若攻击时已叠满则移除全部层数额外造成"
            "（{atk_pct:coef}*攻击力+{agi_pct:coef}*敏捷）物理伤害。",
    "params": {"def_down": 2, "max_stacks": 3, "atk_pct": 30, "agi_pct": 10},
    "auras": [{"target": "foe", "stat": "defense", "op": "down", "value": "foe.stacks.千丝 * def_down"}],
    "triggers": [{"on": "compute_hit", "priority": 200, "if": _NOT_DODGED, "do": [
        {"action": "set_hit", "part": "physical",
         "value": "self.panel.atk * atk_pct // 100 + self.panel.agi * agi_pct // 100",
         "if": "foe.stacks.千丝 >= max_stacks"},
        # 叠满时清空，否则 +1 层
        {"action": "stack", "name": "千丝", "op": "set",
         "value": "0 if foe.stacks.千丝 >= max_stacks else foe.stacks.千丝 + 1"},
    ]}],
})

# 第 8 回合的一击：只按这里写的百分比无视防御/法抗，不用自己的穿透。
# 旧版这一击算目标防御时不算千丝和元素洗礼的减防。
ZHONGMO = EffectDef.model_validate({
    "id": "zhongmo",
    "name": "终末",
    "desc": "战斗开始时，造成的伤害降低{dealt_down}%，受到的伤害降低{taken_down}%，持续{rounds}回合，"
            "第{extra_round}回合开始时，额外造成一次无视{ignore_def}%防御和{ignore_resist}%法抗的伤害。",
    "params": {"dealt_down": 15, "taken_down": 20, "rounds": 7, "extra_round": 8, "ignore_def": 77,
               "ignore_resist": 50},
    "triggers": [
        {"on": "battle_start", "do": [
            {"action": "modify_stat", "stat": "dmg_dealt_down", "op": "add", "value": "dealt_down",
             "rounds": "rounds"},
            {"action": "modify_stat", "stat": "dmg_taken_down", "op": "add", "value": "taken_down",
             "rounds": "rounds"},
        ]},
        {"on": "round_start", "priority": 60, "if": f"{_on_round('extra_round')} and foe.hp_now > 0", "do": [
            {"action": "damage", "kind": "physical", "value": "self.panel.atk", "ignore_def": "ignore_def",
             "not_lowered_by": ["qiansi_yin", "yuansu_xili"], "label": "终末", "if": "not weapon.magic"},
            {"action": "damage", "kind": "magic", "value": "self.mp", "ignore_resist": "ignore_resist",
             "label": "终末", "if": "weapon.magic"},
        ]},
    ],
})

CHENLUN_ZHIYING_4 = EffectDef.model_validate({
    "id": "chenlun_zhiying_4",
    "name": "沉沦之影·4件",
    "desc": "战斗开始时，若敏捷大于目标，则获得{crit_dmg}%暴击伤害和{dodge}%闪避率，闪避率持续{dodge_rounds}回合。"
            "反之攻击无视目标（{pen_agi_pct:coef}*敏捷）防御，持续{pen_rounds}回合",
    "params": {"crit_dmg": 60, "dodge": 30, "dodge_rounds": 3, "pen_agi_pct": 30, "pen_rounds": 5},
    "triggers": [{"on": "battle_start", "do": [
        {"action": "modify_stat", "stat": "crit_dmg", "op": "add", "value": "crit_dmg",
         "if": "self.panel.agi > foe.panel.agi"},
        {"action": "modify_stat", "stat": "dodge", "op": "add", "value": "dodge", "rounds": "dodge_rounds",
         "if": "self.panel.agi > foe.panel.agi"},
        {"action": "modify_stat", "stat": "penetration", "op": "add", "value": "self.panel.agi * pen_agi_pct // 100",
         "rounds": "pen_rounds", "if": "self.panel.agi <= foe.panel.agi"},
    ]}],
})

# 按图鉴修正（2026-11-23 决定）：旧版把 0.065 四舍五入成整数百分比，实际按 6% 算；新版按 6.5% 算。
SHANLUAN = EffectDef.model_validate({
    "id": "shanluan",
    "name": "山峦",
    "desc": "战斗开始时，若敏捷低于对方，则获得{reduce}%免伤，每次攻击后减少{decay}%免伤。"
            "攻击后额外附加（{hp_permille:permille}*生命+{def_pct:coef}*防御）物理伤害",
    "params": {"reduce": 8, "decay": 2, "hp_permille": 65, "def_pct": 20},
    "auras": [{"stat": "dmg_reduce", "op": "add", "value": "self.vars.山峦免伤"}],
    "triggers": [
        {"on": "battle_start", "if": "self.panel.agi < foe.panel.agi", "do": [
            {"action": "flag", "name": "山峦免伤", "value": "reduce"},
        ]},
        {"on": "compute_hit", "if": _NOT_DODGED, "do": [
            {"action": "set_hit", "part": "physical", "value": "self.panel.hp * hp_permille // 1000"},
            {"action": "set_hit", "part": "physical", "value": "self.panel.defense * def_pct // 100"},
        ]},
        {"on": "after_attack", "if": "self.vars.山峦免伤 > 0", "do": [
            {"action": "flag", "name": "山峦免伤", "value": "max(0, self.vars.山峦免伤 - decay)"},
        ]},
    ],
})

BATCH2 = [ZHONGMO_SHIKE_4, ZHAOZE, GUSHU_ZHIXIN, BEIMING_ZHIYING, NVYAO_BEIMING, QIANSI_YIN, ZHONGMO,
          CHENLUN_ZHIYING_4, SHANLUAN]
