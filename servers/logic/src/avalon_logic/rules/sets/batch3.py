"""M3 批次 3：把普通攻击换成指定的攻击（裂空、巡征追猎的二连击、溺梦渊心），以及碎空的周期法术。

和旧版一致的规则：
- 换过的普通攻击按面板属性算数值（不算战斗中的临时加成），各项系数先相加再统一取整一次。
- 多段攻击每段单独判定闪避和暴击，每段按当时的防御结算；全部段都被闪避才算这次攻击被闪避。
- 多个效果都换普通攻击时，优先级小的生效（旧版的先后：多段攻击 → 法术攻击 → 物理攻击）。
- 附加伤害、周期法术多个套装都有时叠加（2026-11-23 决定；旧版只取最大的一个）。
"""

from __future__ import annotations

from avalon_contracts.rules.effect import EffectDef

from .batch1 import _shield

# 旧版"攻击造成（…）伤害"的几种写法，各自的优先级
_HITS_PRIORITY = 50       # 多段攻击（裂空、巡征追猎、群星之子的武器效果）
_MAGIC_PRIORITY = 60      # 法术攻击（溺梦渊心、火纹焚天）


def _hit(kind: str, value: str) -> dict:
    return {"kind": kind, "value": value}


LIEKONG_4 = EffectDef.model_validate({
    "id": "liekong_4",
    "name": "裂空·4件",
    "desc": "攻击造成（{atk_pct:coef}*攻击+{hp_pct:coef}*生命）物理伤害",
    "params": {"atk_pct": 95, "hp_pct": 20},
    "triggers": [{"on": "attack", "priority": _HITS_PRIORITY, "do": [
        # 旧版按"多段攻击"的写法结算（只有一段）：每段单独判定的效果对它按段生效
        {"action": "replace_hit", "multi": True,
         "hits": [_hit("physical", "(self.panel.atk * atk_pct + self.panel.hp * hp_pct) // 100")]},
    ]}],
})

XUNZHENG_ZHUILIE = EffectDef.model_validate({
    "id": "xunzheng_zhuilie",
    "name": "巡征追猎",
    "desc": "攻击变为二连击，每段攻击造成（{atk_pct:coef}*攻击+{agi_pct:coef}*敏捷）物理伤害。",
    "params": {"atk_pct": 48, "agi_pct": 35},
    "triggers": [{"on": "attack", "priority": _HITS_PRIORITY, "do": [
        {"action": "replace_hit", "hits": [
            _hit("physical", "(self.panel.atk * atk_pct + self.panel.agi * agi_pct) // 100"),
            _hit("physical", "(self.panel.atk * atk_pct + self.panel.agi * agi_pct) // 100"),
        ]},
    ]}],
})

# 按图鉴（2026-11-23 决定）：攻击不施加火痕。旧版这件和火纹焚天共用同一种写法，会顺带施加火痕，图鉴没写。
NIMENG_YUANXIN_4 = EffectDef.model_validate({
    "id": "nimeng_yuanxin_4",
    "name": "溺梦渊心·4件",
    "desc": "战斗开始时，获得（{shield_mp_pct:coef}*法力）护盾。攻击造成（{mp_pct:coef}*法力）法术伤害",
    "params": {"shield_mp_pct": 150, "mp_pct": 115},
    "triggers": [
        {"on": "battle_start", "priority": 5, "do": [_shield("开场护盾_法力", "shield_mp_pct")]},
        {"on": "attack", "priority": _MAGIC_PRIORITY, "do": [
            {"action": "replace_hit", "hits": [_hit("magic", "self.panel.mp * mp_pct // 100")]},
        ]},
    ],
})

SUIKONG_4 = EffectDef.model_validate({
    "id": "suikong_4",
    "name": "碎空·4件",
    "desc": "提升{pen}法术穿透。每{cycle_rounds}回合，攻击造成（{magic_mp_pct:coef}*法力）法术伤害并获得"
            "（{shield_mp_pct:coef}*法力）护盾",
    "params": {"pen": 16, "cycle_rounds": 3, "magic_mp_pct": 130, "shield_mp_pct": 50},
    "static": [{"stat": "ignore_magic_resist", "op": "add", "value": "pen"}],
    "triggers": [
        {"on": "compute_hit", "if": "round_no % cycle_rounds == 0 and not hit.dodged", "do": [
            {"action": "set_hit", "part": "magic", "value": "self.panel.mp * magic_mp_pct // 100"},
        ]},
        {"on": "after_attack", "if": "round_no % cycle_rounds == 0 and hit.damage > 0", "do": [
            {"action": "shield", "value": "self.panel.mp * shield_mp_pct // 100"},
        ]},
    ],
})

BATCH3 = [LIEKONG_4, XUNZHENG_ZHUILIE, NIMENG_YUANXIN_4, SUIKONG_4]
