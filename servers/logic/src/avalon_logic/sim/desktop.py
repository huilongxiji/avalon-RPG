"""当前规则库 → 原桌面数据结构。无 Excel 文件、导入步骤或本地图鉴副本。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from avalon_contracts.api.desktop import DesktopCatalog
from avalon_contracts.rules.item import DAMAGE_LABELS, SLOT_LABELS
from avalon_contracts.rules.monster import KIND_LABELS

from .snapshot import DATA, capture

# 仅为原界面保留装备名字的展示字色，不参与规则或数值计算。
COLORS = json.loads(Path(__file__).with_name("desktop_colors.json").read_text(encoding="utf-8"))
BASE_STATS = {"hp", "atk", "defense", "agi", "mp"}
PCT_LABELS = {"hp_pct": "生命", "atk_pct": "攻击", "defense_pct": "防御", "agi_pct": "敏捷", "mp_pct": "法力",
              "crit": "暴击率", "crit_dmg": "暴击伤害", "dodge": "闪避率", "dmg_reduce": "免伤",
              "exp_pct": "经验加成", "drop_pct": "装备掉率"}
PASSIVE_LABELS = {"pen_pct": ("无视", "防御", "%"), "ignore_def_pct": ("无视", "防御", "%"),
                  "ignore_resist_pct": ("无视", "法抗", "%"), "penetration": ("提升", "物理穿透", ""),
                  "ignore_magic_resist": ("提升", "法术穿透", ""), "dmg_pct": ("提升", "增伤", "%")}


def build(version: int, digest: str, snapshot: dict) -> DesktopCatalog:
    data = DATA.validate_python(snapshot)
    effects = {e.id: e for e in data.effects}
    sets = {s.name: s for s in data.sets}
    stat_names = {s.key: s.name for s in data.stats}
    rows, colors = [], {}
    for item in data.items:
        special, passages, extra = [], [], []
        if item.slot == "weapon":
            special.append(DAMAGE_LABELS.get(item.damage_type or "physical", "物理"))
        for key, value in item.stats.items():
            if key in BASE_STATS or not value:
                continue
            if key in PCT_LABELS:
                special.append(f"{value:g}%{PCT_LABELS[key]}")
            elif key in PASSIVE_LABELS:
                prefix, label, suffix = PASSIVE_LABELS[key]
                extra.append(f"{prefix}{value:g}{suffix}{label}。")
            else:
                special.append(f"{value:g}点{stat_names.get(key, key)}")
        for name in item.sets:
            definition = sets[name]
            for tier in definition.tiers:
                text = "。".join(effects[key].render_desc().rstrip("。") for key in tier.effects)
                passages.append(f"{name}：[{tier.pieces}件套]：{text}。")
        for key in item.effects:
            effect = effects[key]
            passages.append(f"{effect.name}：{effect.render_desc()}")
        if extra:
            passages.append(f"{item.name}词条：{''.join(extra)}")
        rows.append([item.id, item.name, SLOT_LABELS[item.slot], item.price,
                     *(item.stats.get(k, 0) for k in ("hp", "atk", "defense", "agi", "mp")),
                     "，".join(special), "\n".join(passages)])
        if color := COLORS.get(f"{item.id}:{item.name}"):
            colors[str(len(rows) + 1)] = color

    monsters = {m.id: m for m in data.monsters}
    placements = {}
    for dungeon in sorted(data.dungeons, key=lambda d: d.id):
        for encounter in dungeon.encounters:
            placements.setdefault(encounter.monster_id, (dungeon.id, dungeon.name, encounter.weight))
        if dungeon.hidden_id:
            placements.setdefault(dungeon.hidden_id, (dungeon.id, dungeon.name, 1))
    monster_rows, drop_rows, drop_rates = [], [], {}
    reserved = {m.no for m in monsters.values() if m.no is not None}
    used = set()
    ordered = sorted(monsters.values(), key=lambda m: (placements.get(m.id, (10**9,))[0],
                                                        m.no if m.no is not None else 10**9, m.id))
    for monster in ordered:
        number = monster.no
        if number is None or number in used:
            number = int(hashlib.sha256(monster.id.encode()).hexdigest()[:12], 16)
            while number in used or number in reserved:
                number += 1
        used.add(number)
        dungeon_id, dungeon_name, weight = placements.get(monster.id, (0, "其他", 1))
        # 归属图鉴中有名字、实际掉落表中没有的物品，不能触发旧客户端默认 20% 掉率。
        rewards = dict.fromkeys(monster.info_rewards, 0.0)
        rewards.update({reward.name: reward.chance / 100 for reward in [*monster.rewards, *monster.prop_rewards]})
        drop_rates[str(number)] = rewards
        drops = list(dict.fromkeys([*monster.info_rewards, *rewards]))
        monster_rows.append([f"{dungeon_id} {dungeon_name}", number, monster.name, KIND_LABELS[monster.kind],
                             monster.level, monster.coins, monster.exp,
                             *(monster.stats.get(k, 0) for k in ("hp", "atk", "defense", "agi", "magic_resist")),
                             None, *drops[:5], *([None] * max(0, 5-len(drops)))])
        drop_rows.append([dungeon_id, number, monster.name, weight, KIND_LABELS[monster.kind],
                          *(value for pair in rewards.items() for value in pair)])
    return DesktopCatalog(rules_version=version, revision=digest, items_rows=rows, monster_rows=monster_rows,
                          drop_rows=drop_rows, item_colors=colors, formulas=data.formulas,
                          rule_data=snapshot, drop_rates=drop_rates)


async def catalog() -> DesktopCatalog:
    return build(*await capture("active"))
