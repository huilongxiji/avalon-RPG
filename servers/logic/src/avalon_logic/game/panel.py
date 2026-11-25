"""玩家的战斗面板：角色属性 + 身上装备（按强化、淬炼换算）+ 套装效果（对应旧版 catalog.combat_stats_from_panel）。"""

from __future__ import annotations

from dataclasses import dataclass, replace

from avalon_contracts.rules.item import DAMAGE_LABELS

from ..engine.battle import FighterSpec, build_player
from . import core, info
from .constants import EQUIP_SLOTS

_CHAR_STATS = ("hp", "atk", "defense", "agi", "mp", "penetration")


@dataclass(frozen=True)
class Worn:
    slot: str
    item_id: int
    name: str
    enhance: int
    temper: int


async def worn_items(openid: str) -> list[Worn]:
    eq = await core.equipped(openid)
    out: list[Worn] = []
    for slot in EQUIP_SLOTS:
        e = eq[slot]
        if e.item_id is not None and core.item(e.item_id) is not None:
            out.append(Worn(slot, e.item_id, core.item_name(e.item_id), e.enhance, e.temper))
    return out


def item_bonuses(items: list[Worn]) -> tuple[int, int]:
    """身上全部装备的经验加成%、装备掉率%（各件累加，例如项链 + 宝石）。"""
    exp = drop = 0
    for w in items:
        stats = core.item(w.item_id).stats  # type: ignore[union-attr]
        exp += int(stats.get("exp_pct", 0))
        drop += int(stats.get("drop_pct", 0))
    return exp, drop


def set_counts(items: list[Worn]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for w in items:
        for name in core.item(w.item_id).sets:  # type: ignore[union-attr]
            counts[name] = counts.get(name, 0) + 1
    return counts


async def battle_spec(openid: str, *, bless_level: int = 0, lifesteal_pct: int = 0,
                      combo_chance: int = 0) -> FighterSpec | None:
    """玩家打怪用的参战数据。bless_level：定制宝石祝福（等级差 -2）；后两个是副本符咒。"""
    player = await core.get_player(openid)
    if player is None:
        return None
    rules = core.rules()
    base: dict[str, float] = {k: getattr(player, k) for k in _CHAR_STATS}
    items = await worn_items(openid)
    damage_type, weapon_id = "physical", ""
    own: list[str] = []
    for w in items:
        item = core.item(w.item_id)
        for key, value in info.item_stats_at(item, w.enhance, w.temper).items():  # type: ignore[arg-type]
            base[key] = base.get(key, 0) + value
        own.extend(item.effects)  # type: ignore[union-attr]
        if w.slot == "weapon":
            weapon_id = str(w.item_id)
            damage_type = item.damage_type or "physical"  # type: ignore[union-attr]
    if bless_level:
        base["bless_level"] = base.get("bless_level", 0) + bless_level
    spec = build_player(rules, level=player.level, base=base, effects=[*own, *rules.set_effects(set_counts(items))],
                        damage_type=damage_type, weapon_id=weapon_id)
    if lifesteal_pct or combo_chance:
        spec = replace(spec, lifesteal_pct=lifesteal_pct, combo_chance=combo_chance)
    return spec


def damage_label(spec: FighterSpec) -> str:
    return DAMAGE_LABELS.get(spec.damage_type, "物理")


def kill_mark_pct(spec: FighterSpec, foe_stacks: dict[str, int], won: bool) -> int:
    """沉沦：胜利时每层沉沦印记加若干 % 装备掉率、经验、代币（效果参数 kill_bonus）。"""
    if not won or not foe_stacks.get("沉沦印记"):
        return 0
    rules = core.rules()
    bonus = sum(int(rules.effects[e].params.get("kill_bonus", 0)) for e, _ in spec.effects if e in rules.effects)
    return foe_stacks["沉沦印记"] * bonus
