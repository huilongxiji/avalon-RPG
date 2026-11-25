"""模拟计算：仅消费规则快照和配装，复用线上引擎，不读写玩家或统计库。"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from typing import Callable

from avalon_contracts.api.sim import Loadout, SimJobRequest
from avalon_contracts.errors import GameError
from avalon_contracts.rules.item import SLOT_LABELS

from ..engine.battle import (
    BattleResult,
    FighterSpec,
    build_monster,
    build_player,
    build_world_boss,
    fight,
)
from ..engine.ruleset import RuleSet
from ..game.info import ENHANCEABLE_SLOTS, item_stats_at
from ..rules import current
from ..rules.game_defaults import DEFAULTS
from .snapshot import DATA

SUPPORTED = ("batch", "matrix", "compare_gear", "world_boss")
METRICS = ("win_rate", "avg_rounds", "avg_remaining_hp", "avg_player_damage", "avg_foe_damage",
           "crit_rate", "dodge_rate")


def player(rules: RuleSet, loadout: Loadout) -> tuple[FighterSpec, list[dict]]:
    # 与新角色的初始属性、升级增量一致；模拟角色没有签到、赞助或管理员附加属性。
    base = {"hp": 100 + (loadout.level - 1) * rules.setting("hp_per_level", DEFAULTS["hp_per_level"]),
            "atk": 10 + (loadout.level - 1) * rules.setting("atk_per_level", DEFAULTS["atk_per_level"]),
            "defense": 5, "agi": 5, "mp": 10, "penetration": 0}
    slots = {label: key for key, label in SLOT_LABELS.items()}
    occupied: set[str] = set()
    own: list[str] = []
    sets: Counter = Counter()
    equipment = []
    weapon_id, damage_type = "", "physical"
    with current.using(rules):
        for label, piece in loadout.gear.items():
            slot = slots.get(label, label)
            item = rules.items.get(piece.item_id)
            if slot not in ("weapon", "armor", "bracelet", "necklace", "gem") or slot in occupied:
                raise GameError("invalid", f"装备部位无效或重复：{label}")
            if item is None or item.slot != slot:
                raise GameError("invalid", f"装备 {piece.item_id} 不存在或不属于 {label}")
            if slot not in ENHANCEABLE_SLOTS and (piece.enhance or piece.temper):
                raise GameError("invalid", f"{label} 不能强化或淬炼")
            if piece.enhance > 200 or piece.temper > rules.setting("temper_cap_pct", DEFAULTS["temper_cap_pct"]):
                raise GameError("invalid", "强化超过模拟支持范围（0～200）或淬炼超过规则上限")
            occupied.add(slot)
            stats = item_stats_at(item, piece.enhance, piece.temper)
            for key, value in stats.items():
                base[key] = base.get(key, 0) + value
            own.extend(item.effects)
            sets.update(item.sets)
            equipment.append({"slot": slot, "item_id": item.id, "name": item.name, "stats": stats,
                              "enhance": piece.enhance, "temper": piece.temper})
            if slot == "weapon":
                weapon_id, damage_type = str(item.id), item.damage_type or "physical"
    spec = build_player(rules, level=loadout.level, base=base,
                        effects=[*own, *rules.set_effects(sets)], damage_type=damage_type,
                        weapon_id=weapon_id, name=loadout.name)
    return spec, equipment


def stats(rules: RuleSet, loadout: Loadout) -> dict:
    spec, equipment = player(rules, loadout)
    return {"rules_version": rules.version_id, "level": spec.level, "name": spec.name,
            "panel": dict(spec.panel), "base": dict(spec.base), "damage_type": spec.damage_type,
            "equipment": equipment, "effects": [
                {"id": key, "name": rules.effects[key].name, "pieces": count,
                 "description": rules.effects[key].desc}
                for key, count in spec.effects], "pity_enabled": False}


def target(rules: RuleSet, value: str, level: int) -> FighterSpec:
    if value == "world_boss":
        return build_world_boss(rules, level)
    key = value.removeprefix("monster:")
    if value.startswith("dungeon:"):
        parts = value.split(":")
        if len(parts) != 3 or not parts[1].isdigit():
            raise GameError("invalid", "副本对手格式应为 dungeon:编号:boss（或 normal、elite、hidden）")
        dungeon = rules.dungeons.get(int(parts[1]))
        if dungeon is None:
            raise GameError("not_found", "副本不存在")
        ids = ([dungeon.hidden_id] if parts[2] == "hidden" else
               [e.monster_id for e in dungeon.encounters if rules.monsters[e.monster_id].kind == parts[2]])
        if not ids or not ids[0]:
            raise GameError("not_found", "副本没有该类型的怪物")
        key = ids[0]
    monster = rules.monsters.get(key)
    if monster is None:
        raise GameError("not_found", f"怪物不存在：{value}")
    return build_monster(rules, monster)


def validate(rules: RuleSet, request: SimJobRequest) -> None:
    if request.type not in SUPPORTED:
        raise GameError("invalid", f"当前支持的模拟场景：{'、'.join(SUPPORTED)}；{request.type} 尚未接入")
    if not request.targets:
        raise GameError("invalid", "请至少选择一个对手")
    if request.type == "compare_gear" and len(request.loadouts) < 2:
        raise GameError("invalid", "配装对比至少需要两套配装，第一套作为基准")
    if request.type == "world_boss" and request.targets != ["world_boss"]:
        raise GameError("invalid", "世界 BOSS 场景的对手必须为 world_boss")
    for loadout in request.loadouts:
        player(rules, loadout)
    for name in request.targets:
        target(rules, name, request.loadouts[0].level)


class Summary:
    """流式汇总；不保留每一场的战报或每次命中的数组。"""

    def __init__(self):
        self.count = self.wins = self.losses = self.draws = self.close_wins = 0
        self.rounds = self.hp = self.player_damage = self.foe_damage = 0
        self.player_turns = self.foe_turns = self.crits = self.dodges = 0
        self.extrema: dict[str, list[int]] = {}
        self.effects: Counter = Counter()

    def _range(self, key: str, value: int):
        bounds = self.extrema.setdefault(key, [value, value])
        bounds[0], bounds[1] = min(bounds[0], value), max(bounds[1], value)

    def add(self, result: BattleResult):
        self.count += 1
        draw = result.draw or result.timeout
        self.wins += int(result.won)
        self.draws += int(draw)
        self.losses += int(not result.won and not draw)
        self.close_wins += int(result.won and result.player_hp <= result.player_max_hp * .1)
        self.rounds += result.rounds
        self.hp += max(0, result.player_hp)
        damage = {"player": 0, "monster": 0}
        for turn in result.turns:
            damage[turn.side] += turn.total
            self._range(f"{turn.side}_hit", turn.total)
            if turn.side == "player":
                self.player_turns += 1
            else:
                self.foe_turns += 1
        self.crits += result.player_crits
        self.dodges += result.player_dodges
        self.player_damage += damage["player"]
        self.foe_damage += damage["monster"]
        self.effects.update(result.triggered)
        for key, value in (("rounds", result.rounds), ("remaining_hp", max(0, result.player_hp)),
                           ("player_damage", damage["player"]), ("foe_damage", damage["monster"])):
            self._range(key, value)

    def report(self) -> dict:
        n = self.count or 1
        return {"count": self.count, "wins": self.wins, "losses": self.losses, "draws": self.draws,
                "win_rate": self.wins / n, "close_wins": self.close_wins,
                "avg_rounds": self.rounds / n, "avg_remaining_hp": self.hp / n,
                "avg_player_damage": self.player_damage / n, "avg_foe_damage": self.foe_damage / n,
                "crit_rate": self.crits / self.player_turns if self.player_turns else 0,
                "dodge_rate": self.dodges / self.foe_turns if self.foe_turns else 0,
                "ranges": self.extrema, "effects": dict(self.effects)}


def run(snapshot: dict, version: int, digest: str, body: dict,
        progress: Callable[[int, int], None] | None = None) -> dict:
    rules = DATA.validate_python(snapshot).compile(version)
    request = SimJobRequest.model_validate(body)
    validate(rules, request)
    cells, samples = [], []
    done, total = 0, request.runs * len(request.loadouts) * len(request.targets)
    for index, loadout in enumerate(request.loadouts):
        spec, _ = player(rules, loadout)
        for target_name in request.targets:
            foe = target(rules, target_name, loadout.level)
            groups = {name: Summary() for name in ("all", "win", "loss", "draw")}
            for repeat in range(request.runs):
                # 各配装、各版本使用同一批种子，排序和队列并发不改变结果。
                result = fight(rules, spec, foe, seed=request.seed + repeat,
                               max_rounds=request.params.max_rounds)
                group = "win" if result.won else "draw" if result.draw or result.timeout else "loss"
                groups["all"].add(result)
                groups[group].add(result)
                done += 1
                if progress and (done % 10 == 0 or done == total):
                    progress(done, total)
            cells.append({"loadout_index": index, "loadout_name": loadout.name, "target": target_name,
                          "groups": {name: summary.report() for name, summary in groups.items()}})
            # 最多保留 10 个格子的最后一场，避免矩阵任务把整个历史塞进内存。
            if len(samples) < 10:
                samples.append({"loadout_index": index, "target": target_name,
                                "seed": request.seed + request.runs - 1, "battle": asdict(result)})
    gear_differences = []
    if request.type == "compare_gear":
        baseline = {cell["target"]: cell for cell in cells if cell["loadout_index"] == 0}
        for cell in cells:
            if cell["loadout_index"] > 0:
                gear_differences.extend(_differences(baseline[cell["target"]], cell, 5))
    return {"type": request.type, "rules_version": version, "rules_digest": digest,
            "seed": request.seed, "runs": request.runs, "params": request.params.model_dump(),
            "loadouts": [x.model_dump() for x in request.loadouts], "targets": request.targets,
            "pity_enabled": False, "cells": cells, "samples": samples, "gear_differences": gear_differences}


def _differences(left: dict, right: dict, threshold: float) -> list[dict]:
    differences = []
    for key in METRICS:
        old, new = left["groups"]["all"][key], right["groups"]["all"][key]
        pct = (new - old) / abs(old) * 100 if old else (0 if not new else None)
        differences.append({"loadout_index": right["loadout_index"], "target": right["target"],
                            "metric": key, "before": old, "after": new, "delta": new - old,
                            "change_pct": pct, "flagged": pct is None or abs(pct) > threshold})
    return differences


def compare(a: dict, b: dict, threshold: float) -> dict:
    for key in ("type", "seed", "runs", "params", "loadouts", "targets"):
        if a[key] != b[key]:
            raise GameError("invalid", f"版本对比要求相同的场景、配装、种子和次数；{key} 不一致")
    differences = []
    for left, right in zip(a["cells"], b["cells"], strict=True):
        differences.extend(_differences(left, right, threshold))
    return {"rules_a": a["rules_version"], "rules_b": b["rules_version"],
            "digest_a": a["rules_digest"], "digest_b": b["rules_digest"],
            "threshold_pct": threshold, "differences": differences}
