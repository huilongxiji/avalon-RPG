"""从规则数据推出来的游戏资料：强化费用和系数、淬炼、分解、隐秘宝石、遇怪、掉落、保底
（对应旧版 dungeon/catalog.py、dungeon/enhance.py 里不碰数据库的函数，算法完全一致）。"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass

from avalon_contracts.rules.item import ItemDef
from avalon_contracts.rules.monster import DungeonDef, Encounter, MonsterDef, Reward

from ..engine.ruleset import RuleSet
from . import core, tuning

# ---------------------------------------------------------------- 强化、淬炼

ENHANCE_COST_BASE = 200
ENHANCE_COST_GROWTH = 1.5
ENHANCE_REFUND_RATE = 75
MARKET_MIN_PERCENT = 50
ENHANCEABLE_SLOTS = ("weapon", "armor", "bracelet", "necklace")
TEMPER_BASE_DUNGEON = 5
TEMPER_BASE_LEVEL = 10
TEMPER_CRAFTED_BONUS = 1
TEMPER_COIN_RATE = 34
TEMPER_CAP_PCT = 10
TEMPER_ROLL_MIN = 1
TEMPER_ROLL_MAX = 5
BASIC_STAT_KEYS = ("hp", "atk", "defense", "agi", "mp")


def _round_half_up(value: float) -> int:
    return int(math.floor(value + 0.5))


def enhance_step_cost(level: int) -> int:
    """从当前强化等级升到下一级所需代币。"""
    if level < 0:
        raise ValueError("强化等级不能为负")
    return int(tuning.formula('enhance_step_cost', level=level, base=tuning.value('enhance_cost_base'), growth=tuning.value('enhance_cost_growth')))


def enhance_total_cost(level: int) -> int:
    if level < 0:
        raise ValueError("强化等级不能为负")
    return sum(enhance_step_cost(n) for n in range(level))


def enhance_cost_to(start: int, target: int) -> list[int]:
    if start < 0 or target < start:
        raise ValueError("强化目标无效")
    return [enhance_step_cost(n) for n in range(start, target)]


def enhance_refund(level: int) -> int:
    return enhance_total_cost(level) * tuning.value('enhance_refund_rate') // 100


def enhance_multiplier(level: int) -> float:
    if level < 0:
        raise ValueError("强化等级不能为负")
    return float(tuning.formula('enhance_stat_mult', level=level))


def enhance_success_chance(level: int) -> float:
    """10 级起 P(n) = 0.5 + 0.45·e^(-0.15·(n-10))，10 级前必定成功。"""
    if level < 0:
        raise ValueError("强化等级不能为负")
    return min(1.0, float(tuning.formula('enhance_success', level=level)))


def attempt_enhance(level: int) -> bool:
    return random.random() < enhance_success_chance(level)


def enhance_progress(start: int, target: int, roll: Callable[[int], bool]) -> tuple[int, list[int], int | None]:
    """逐级判定强化。返回 (新等级, 已尝试费用列表, 失败等级或 None)；某一级失败即停在该级。"""
    if start < 0 or target < start:
        raise ValueError("强化目标无效")
    level = start
    spent: list[int] = []
    failed_at: int | None = None
    while level < target:
        spent.append(enhance_step_cost(level))
        if enhance_success_chance(level) >= 1 or roll(level):
            level += 1
        else:
            failed_at = level
            break
    return level, spent, failed_at


def temper_scale(base: float, temper_pct: int) -> float:
    if temper_pct <= 0:
        return float(base)
    return base * (100 + min(tuning.value('temper_cap_pct'), max(0, temper_pct))) / 100


def temper_base(base: int, temper_pct: int) -> int:
    if temper_pct <= 0:
        return base
    return int(base * (100 + min(tuning.value('temper_cap_pct'), max(0, temper_pct))) / 100)


def stat_at(base: float, key: str, level: int, temper: int = 0) -> int:
    """强化、淬炼后的一项属性：只有生命、攻击、防御、敏捷、法力受影响。
    淬炼保留小数与强化系数乘算，+0 时截断（6.6→6），强化后按 ceil 取整（7.26→8）。"""
    if key not in BASIC_STAT_KEYS:
        return int(base)
    value = temper_scale(int(base), temper) * enhance_multiplier(level)
    if level <= 0:
        return int(value)
    if value > 0:
        return math.ceil(value - 1e-9)
    if value < 0:
        return math.floor(value + 1e-9)
    return 0


def item_stats_at(item: ItemDef, level: int, temper: int = 0) -> dict[str, int]:
    return {key: stat_at(value, key, level, temper) for key, value in item.stats.items()}


def temper_baseline_level(dungeon_id: int, crafted: bool) -> int:
    return tuning.value('temper_base_level') + max(0, int(dungeon_id) - tuning.value('temper_base_dungeon')) + (tuning.value('temper_crafted_bonus') if crafted else 0)


def temper_coin_cost(dungeon_id: int, crafted: bool) -> int:
    return enhance_step_cost(temper_baseline_level(dungeon_id, crafted)) * tuning.value('temper_coin_rate') // 100


def market_min_price(base_price: int, level: int) -> int:
    return (max(0, base_price) * tuning.value('market_min_percent') + enhance_total_cost(level) * tuning.value('market_min_percent')) // 100


# ---------------------------------------------------------------- 装备、副本归属

EQUIP_SLOTS = ("weapon", "armor", "bracelet", "necklace", "gem")
EQUIP_BOX_SLOTS = ("weapon", "armor", "bracelet", "necklace")
KIND_LABEL = {"normal": "普通", "elite": "精英", "boss": "BOSS", "hidden": "隐秘"}
KIND_RANK = {"normal": 0, "elite": 1, "boss": 2, "hidden": 3}
PITY_GAIN = {"normal": 1, "elite": 2, "boss": 3, "hidden": 5}
PITY_PER_DUNGEON = 25
PITY_GEM_PER_DUNGEON = 17
DROP_ROLL_SCALE = 10000
ESSENCE_PER_BOX = 3


def is_equipment(name: str) -> bool:
    found = core.item_by_name(name)
    return found is not None and found.slot in EQUIP_SLOTS


def is_box_equipment(name: str) -> bool:
    """礼盒能开出的装备：只认四个装备部位，宝石、材料、道具都不算。"""
    found = core.item_by_name(name)
    return found is not None and found.slot in EQUIP_BOX_SLOTS


def equipment_price(name: str) -> int | None:
    found = core.item_by_name(name)
    if found is None or found.slot not in EQUIP_SLOTS:
        return None
    return max(0, found.price)


def monster(monster_id: str | None) -> MonsterDef | None:
    return core.rules().monsters.get(monster_id) if monster_id else None


def dungeon(dungeon_id: int) -> DungeonDef | None:
    return core.rules().dungeons.get(dungeon_id)


def dungeon_by_name(name: str) -> DungeonDef | None:
    return core._index().dungeons_by_name.get(name)


def sorted_dungeons() -> list[DungeonDef]:
    return [d for _, d in sorted(core.rules().dungeons.items())]


def find_monster(name: str) -> MonsterDef | None:
    return next((m for m in core.rules().monsters.values() if m.name == name), None)


class _Derived:
    def __init__(self, rules: RuleSet) -> None:
        drops: dict[str, int] = {}
        for d in sorted(rules.dungeons.values(), key=lambda x: x.id):
            ids = [e.monster_id for e in d.encounters] + ([d.hidden_id] if d.hidden_id else [])
            for mid in ids:
                m = rules.monsters.get(mid)
                if m is None:
                    continue
                for reward in (*m.rewards, *m.prop_rewards):
                    drops.setdefault(reward.name, d.id)
        self.drop_dungeons = drops


def _d() -> _Derived:
    return core.per_rules(core.rules(), "derived", _Derived)


@dataclass(frozen=True)
class DecomposeInfo:
    kind: str
    boss_name: str = ""
    dungeon_id: int = 0
    essence: str = ""
    pity: int = 0


def decompose_info(name: str) -> DecomposeInfo | None:
    """能分解的装备：属于某个首领的装备（先看怪物信息里的归属，没有再看掉落表）→ 这个首领的精华。宝石不能分解。"""
    found = core.item_by_name(name)
    if found is None or found.slot not in EQUIP_SLOTS or found.slot == "gem":
        return None
    for pass_no in (1, 2):
        for d in sorted_dungeons():
            for entry in d.encounters:
                m = monster(entry.monster_id)
                if m is None or m.kind != "boss":
                    continue
                owned = name in m.info_rewards if pass_no == 1 else any(r.name == name for r in m.rewards)
                if owned:
                    return DecomposeInfo(kind="boss", boss_name=m.name, dungeon_id=d.id, essence=f"{m.name}精华")
    return None


def hidden_gem_dungeon(name: str) -> int:
    """隐秘宝石（副本隐秘怪掉落的宝石）所属副本编号；不是隐秘宝石返回 0。"""
    found = core.item_by_name(name)
    if found is None or found.slot != "gem":
        return 0
    for d in sorted_dungeons():
        m = monster(d.hidden_id)
        if m is not None and any(r.name == name for r in m.rewards):
            return d.id
    return 0


def _crafted_dungeon(name: str, seen: set[str]) -> int:
    if name in seen:
        return 0
    seen.add(name)
    best = 0
    for recipe in core.rules().recipes.values():
        if recipe.output != name:
            continue
        for entry in recipe.inputs:
            if not is_equipment(entry.name):
                continue
            best = max(best, _d().drop_dungeons.get(entry.name) or _crafted_dungeon(entry.name, seen))
    return best


def item_dungeon_id(name: str) -> int:
    """装备所属副本：掉落装备取最低掉落副本，合成装备取材料里最高的副本；没有归属返回 0。"""
    if not is_equipment(name):
        return 0
    return _d().drop_dungeons.get(name) or _crafted_dungeon(name, set())


def is_crafted_item(name: str) -> bool:
    return any(r.output == name for r in core.rules().recipes.values())


def dungeon_hidden_gem(dungeon_id: int) -> str:
    """副本隐秘怪掉落的第一颗宝石（淬炼消耗）；没有返回空。"""
    d = dungeon(dungeon_id)
    m = monster(d.hidden_id) if d else None
    if m is None:
        return ""
    for reward in m.rewards:
        found = core.item_by_name(reward.name)
        if found is not None and found.slot == "gem":
            return reward.name
    return ""


def bosses_from(dungeons: list[DungeonDef], monsters: dict[str, MonsterDef],
                box_equipment: Callable[[str], bool]) -> list[tuple[str, tuple[str, ...]]]:
    """首领自选礼盒内容：先按怪物信息归属，没有首领归属的掉落按掉落表兜底（迁移工具导入道具时也用它）。"""
    owned: set[str] = set()
    bosses: list[tuple[int, MonsterDef]] = []
    for d in sorted(dungeons, key=lambda x: x.id):
        for entry in d.encounters:
            m = monsters.get(entry.monster_id)
            if m is None or m.kind != "boss":
                continue
            owned.update(m.info_rewards)
            bosses.append((d.id, m))
    rows: list[tuple[int, str, tuple[str, ...]]] = []
    for dungeon_id, m in bosses:
        names: list[str] = []
        seen: set[str] = set()
        for name in m.info_rewards:
            if name in seen or not box_equipment(name):
                continue
            seen.add(name)
            names.append(name)
        for reward in m.rewards:
            if reward.name in owned or reward.name in seen or not box_equipment(reward.name):
                continue
            seen.add(reward.name)
            names.append(reward.name)
        rows.append((dungeon_id, m.name, tuple(names)))
    rows.sort(key=lambda row: (row[0], row[1]))
    return [(name, equips) for _, name, equips in rows]


def list_bosses() -> list[tuple[str, tuple[str, ...]]]:
    r = core.rules()
    return core.per_rules(r, "bosses", lambda r: bosses_from(list(r.dungeons.values()), dict(r.monsters),
                                                             is_box_equipment))


def boss_equipment(boss_name: str) -> tuple[str, ...]:
    return next((equips for name, equips in list_bosses() if name == boss_name), ())


def equipment_in_dungeon(dungeon_name: str) -> list[str]:
    d = dungeon_by_name(dungeon_name)
    if d is None:
        return []
    ids = [e.monster_id for e in d.encounters] + ([d.hidden_id] if d.hidden_id else [])
    names: list[str] = []
    for mid in ids:
        m = monster(mid)
        for reward in m.rewards if m else ():
            if reward.name not in names and is_equipment(reward.name):
                names.append(reward.name)
    return names


def equipment_by_kind(dungeon_name: str) -> dict[str, list[str]]:
    """小怪、精英、首领各自的装备（四个部位，不含宝石与材料，不含隐秘）。"""
    pools: dict[str, list[str]] = {"normal": [], "elite": [], "boss": []}
    d = dungeon_by_name(dungeon_name)
    if d is None:
        return pools
    for entry in d.encounters:
        m = monster(entry.monster_id)
        if m is None or m.kind not in pools:
            continue
        for reward in m.rewards:
            if reward.name not in pools[m.kind] and is_box_equipment(reward.name):
                pools[m.kind].append(reward.name)
    return pools


# ---------------------------------------------------------------- 遇怪


def sorted_encounters(d: DungeonDef) -> list[Encounter]:
    """副本里的怪按 普通→精英→BOSS、再按图鉴编号排（没有编号的按怪物表里的顺序；旧版 catalog.sorted_encounters）。"""
    order = {mid: n for n, mid in enumerate(core.rules().monsters)}

    def key(entry: Encounter) -> tuple[int, int]:
        m = monster(entry.monster_id)
        number = m.no if m and m.no is not None else order.get(entry.monster_id, 0)
        return KIND_RANK.get(m.kind if m else "", 9), number
    return sorted(d.encounters, key=key)


@dataclass(frozen=True)
class GuideMonster:
    name: str
    kind: str
    level: int
    weight: int
    coins: int
    exp: int
    pool: tuple[tuple[str, float], ...]     # (名字, 掉率%)：装备/材料在前、道具在后


@dataclass(frozen=True)
class DungeonGuide:
    id: int
    name: str
    stamina: int
    monsters: tuple[GuideMonster, ...]
    festival: tuple[str, int] | None = None   # 节日活动额外奖池（名字, 最多几个）
    pity: int = 0
    threshold: int = 0


def dungeon_guide(dungeon_id: int, *, pity: int = 0, gem_pity: bool = False) -> DungeonGuide | None:
    """副本图鉴 / 副本列表的一项（不含隐秘怪），文字排版由机器人做（旧版 format_dungeon_detail/list）。"""
    d = dungeon(dungeon_id)
    if d is None:
        return None
    rows: list[GuideMonster] = []
    for entry in sorted_encounters(d):
        m = monster(entry.monster_id)
        if m is None:
            continue
        pool = tuple((r.name, r.chance) for r in (*m.rewards, *m.prop_rewards))
        rows.append(GuideMonster(m.name, m.kind, m.level, entry.weight, m.coins, m.exp, pool))
    threshold = gem_pity_threshold(d) if gem_pity else pity_threshold(d)
    return DungeonGuide(d.id, d.name, d.stamina, tuple(rows), festival_drop(), max(0, int(pity)), threshold)


def dungeon_list(*, pity: int = 0, gem_pity: bool = False) -> list[DungeonGuide]:
    return [g for d in sorted_dungeons() if (g := dungeon_guide(d.id, pity=pity, gem_pity=gem_pity))]


def bless_exp_pct(highest_dungeon: int, level: int, monster_level: int) -> int:
    """定制宝石祝福的经验加成：(5 + 4×最高本 − 0.8×等级)% 向下取整，最低 0；平级或高于目标时减半；
    等级 ≥ 最高本×5−5 时打低等级怪没有加成。"""
    if level >= highest_dungeon * 5 - 5 and level > monster_level:
        return 0
    full = 5 + 4 * highest_dungeon - (8 * level + 9) // 10
    if full <= 0:
        return 0
    return full // 2 if level >= monster_level else full


def cross_dungeon_for(monster_id: str, level: int) -> DungeonDef | None:
    """跨界符：怪物所在的编号最小、已解锁（副本号×5+2 级）的副本。"""
    for d in sorted_dungeons():
        if level < d.id * 5 + 2:
            continue
        if any(e.monster_id == monster_id for e in d.encounters):
            return d
    return None


def _distribute_weights(total: int, entries: list[Encounter]) -> list[int]:
    weights = [e.weight for e in entries]
    share = sum(weights)
    if share <= 0:
        base, rem = divmod(total, len(entries))
        return [base + (1 if i < rem else 0) for i in range(len(entries))]
    exact = [total * w / share for w in weights]
    floors = [int(v) for v in exact]
    leftover = total - sum(floors)
    order = sorted(range(len(entries)), key=lambda i: exact[i] - floors[i], reverse=True)
    for i in order[:leftover]:
        floors[i] += 1
    return floors


def _kind(entry: Encounter) -> str:
    m = monster(entry.monster_id)
    return m.kind if m else ""


def pick_encounter(d: DungeonDef, *, reduce_normal: bool = False, kind: str | None = None) -> MonsterDef:
    """按权重随机遇怪。reduce_normal（年卡）时小怪权重 -10%，削减部分平均分给精英和 BOSS；
    kind（引魔符）限定怪物类型，没有这类怪时用全部。"""
    entries = list(d.encounters)
    if kind is not None:
        filtered = [e for e in entries if _kind(e) == kind]
        if filtered:
            entries = filtered
    if reduce_normal:
        normals = [e for e in entries if _kind(e) == "normal"]
        elites = [e for e in entries if _kind(e) == "elite"]
        bosses = [e for e in entries if _kind(e) == "boss"]
        if normals and (elites or bosses):
            weights = {e.monster_id: e.weight for e in entries}
            freed = 0
            for e in normals:
                reduced = e.weight * (100 - tuning.value('year_normal_weight_reduction_pct')) // 100
                freed += e.weight - reduced
                weights[e.monster_id] = reduced
            if elites and bosses:
                buckets, split = [elites, bosses], [freed // 2, freed - freed // 2]
            elif elites:
                buckets, split = [elites], [freed]
            else:
                buckets, split = [bosses], [freed]
            for bucket, amount in zip(buckets, split, strict=True):
                for e, add in zip(bucket, _distribute_weights(amount, bucket), strict=True):
                    weights[e.monster_id] += add
            entries = [Encounter(monster_id=e.monster_id, weight=weights[e.monster_id]) for e in entries]
    total = sum(e.weight for e in entries)
    roll = random.randrange(total)
    acc = 0
    for e in entries:
        acc += e.weight
        if roll < acc:
            return monster(e.monster_id)  # type: ignore[return-value]
    return monster(entries[-1].monster_id)  # type: ignore[return-value]


def pick_boss(d: DungeonDef) -> MonsterDef:
    pool = [e for e in d.encounters if _kind(e) == "boss"]
    if not pool:
        return pick_encounter(d)
    if len(pool) == 1:
        return monster(pool[0].monster_id)  # type: ignore[return-value]
    total = sum(e.weight for e in pool)
    roll = random.randrange(total)
    acc = 0
    for e in pool:
        acc += e.weight
        if roll < acc:
            return monster(e.monster_id)  # type: ignore[return-value]
    return monster(pool[-1].monster_id)  # type: ignore[return-value]


def roll_hidden(d: DungeonDef, *, certain: bool = False, hidden_bonus: int = 0) -> MonsterDef | None:
    if not d.hidden_id:
        return None
    rate = int(d.hidden_rate * (100 + hidden_bonus) // 100)
    if not certain and rate <= 0:
        return None
    if not certain and random.randrange(100) >= rate:
        return None
    return monster(d.hidden_id)


# ---------------------------------------------------------------- 保底、掉落


def pity_threshold(d: DungeonDef) -> int:
    return int(tuning.formula('pity_threshold', dungeon_id=d.id, per_dungeon=tuning.value('pity_per_dungeon')))


def gem_pity_threshold(d: DungeonDef) -> int:
    """定制宝石"额外保底值"：保底需求从 25×副本序号 降到 17×副本序号。"""
    return int(tuning.formula('pity_threshold', dungeon_id=d.id, per_dungeon=tuning.value('pity_gem_per_dungeon')))


def pity_drop_cut(d: DungeonDef, gem_pity: bool = False) -> int:
    return (gem_pity_threshold(d) if gem_pity else pity_threshold(d)) // 2


def next_pity(current: int, m: MonsterDef, dropped: list[str], d: DungeonDef, *, forced: bool = False,
              gem_pity: bool = False) -> int:
    value = max(0, int(current))
    dropped_equip = sum(1 for name in dropped if is_equipment(name))
    if m.kind == "hidden":
        return 0 if dropped_equip else value + tuning.value('pity_gain')["hidden"]
    if forced:
        if dropped_equip:
            threshold = gem_pity_threshold(d) if gem_pity else pity_threshold(d)
            return max(0, value - threshold * dropped_equip)
        return value
    if m.kind == "boss":
        value += tuning.value('pity_gain')["boss"]
        return max(0, value - pity_drop_cut(d, gem_pity) * dropped_equip) if dropped_equip else value
    return value + tuning.value('pity_gain').get(m.kind, tuning.value('pity_gain')["normal"])


def equip_rewards(m: MonsterDef) -> list[Reward]:
    return [r for r in m.rewards if is_box_equipment(r.name)]


def _kept_roll(chance: float, keep: int) -> int:
    return round(chance * 100) * keep // 100


def compound_bonus(a: int, b: int) -> int:
    return a + b + a * b // 100


def roll_loot(m: MonsterDef, *, guarantee_equip: bool = False, keep: int = 100, special_bonus: int = 0,
              gear_bonus: int = 0, mark_bonus: int = 0) -> list[str]:
    """最终掉率 = 基础掉率 × 装备掉率 × 特殊掉率（规则见旧版 catalog.roll_loot）。"""
    dropped: list[str] = []
    for entry in m.rewards:
        special = special_bonus + keep - 100
        bonus = special
        found = core.item_by_name(entry.name)
        if found is not None and found.slot in EQUIP_SLOTS and found.slot != "gem":
            bonus = compound_bonus(gear_bonus, special) + mark_bonus
        final = _kept_roll(entry.chance, 100) + _kept_roll(entry.chance, bonus)
        if special_bonus > 0 and 0 < final < DROP_ROLL_SCALE // 100:
            final = DROP_ROLL_SCALE // 100
        if random.randrange(DROP_ROLL_SCALE) < final:
            dropped.append(entry.name)
    if guarantee_equip and not any(is_box_equipment(name) for name in dropped):
        pool = equip_rewards(m)
        if pool:
            weights = [max(1, round(e.chance * 100)) for e in pool]
            dropped.append(random.choices(pool, weights=weights, k=1)[0].name)
    return dropped


def roll_prop_loot(m: MonsterDef, *, keep: int = 100) -> list[str]:
    return [e.name for e in m.prop_rewards if random.randrange(DROP_ROLL_SCALE) < _kept_roll(e.chance, keep)]


def apply_percent(base: int, percent: int, *, min_value: int = 0) -> int:
    return max(min_value, base * (100 + percent) // 100)


# ---------------------------------------------------------------- 运行时开关（超管指令设置，重启后清空）

_forced_boss_hidden: set[str] = set()
_festival: tuple[str, int] | None = None


def force_boss_hidden(openid: str) -> None:
    previous = openid in _forced_boss_hidden
    core.on_rollback(lambda: _forced_boss_hidden.add(openid) if previous else _forced_boss_hidden.discard(openid))
    _forced_boss_hidden.add(openid)


def clear_boss_hidden(openid: str) -> None:
    previous = openid in _forced_boss_hidden
    core.on_rollback(lambda: _forced_boss_hidden.add(openid) if previous else _forced_boss_hidden.discard(openid))
    _forced_boss_hidden.discard(openid)


def boss_hidden_forced(openid: str) -> bool:
    return openid in _forced_boss_hidden


def set_festival(name: str, max_qty: int) -> None:
    global _festival
    previous = _festival
    def undo():
        global _festival
        _festival = previous
    core.on_rollback(undo)
    _festival = (name, max_qty)


def clear_festival() -> None:
    global _festival
    previous = _festival
    def undo():
        global _festival
        _festival = previous
    core.on_rollback(undo)
    _festival = None


def festival_drop() -> tuple[str, int] | None:
    if _festival is None:
        return None
    name, cap = _festival
    return name, random.randint(1, cap)
