"""战斗内核（设计文档 7.7 节）。

代码只负责"流程"：谁先出手、什么时候触发哪个时机、动作怎么执行；
所有数值都来自规则：伤害每一步是一个有名字的公式，装备效果是"时机 + 条件 + 动作"的数据。

流程与旧版 bot（old_data/src/plugins/dungeon/combat.py）一致，掷随机数的顺序也一致，
所以同一个种子下新旧引擎的战斗结果完全相同（见 tests/engine/test_parity_old.py）。

一场战斗：
    战斗开始（只在"入场"的战斗触发；爬塔连战的后续战斗不触发）
    每回合：
        回合开始
        先手方出手 → 后手方出手；任何一方倒下就结束
            一次出手：主攻击（闪避判定 → 暴击判定 → 增伤）
                      → 命中后 / 暴击后（伤害结算前）→ 扣血 → 攻击结算后 → 击杀
                      → 对方：闪避后 / 受到攻击后 / 血量下降后
        回合结束 → 限时效果的回合数 -1
    战斗结束
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from avalon_contracts.rules.monster import MonsterDef

from .expr import FORMULAS_KEY, ZeroDict
from .rng import Rng
from .ruleset import Action, Effect, RuleSet, Trigger, to_number

PLAYER = "player"
MONSTER = "monster"
MAX_ACTIONS = 20000           # 每场战斗最多执行多少个动作（防止规则写出死循环）
MAX_DEPTH = 30                # 效果互相触发（比如叠层时又叠层）最多嵌套多少层
DAMAGE_TYPES = ("physical", "magic", "precision")


class BattleError(RuntimeError):
    """规则在战斗中出错（比如动作执行次数超过上限）。"""


# ---------------------------------------------------------------- 参战方的准备


@dataclass(frozen=True)
class FighterSpec:
    """一名参战者开战前的样子：面板属性 + 身上的效果。"""

    side: str                                   # player / monster
    name: str
    level: int
    panel: Mapping[str, float]                  # 面板属性（已加完装备和静态加成）
    base: Mapping[str, float]                   # 基础属性（百分比加成之前）
    effects: tuple[tuple[str, int], ...] = ()   # (效果代号, 套装件数)
    damage_type: str = "physical"
    world_boss: bool = False
    weapon_id: str = ""                         # 武器的装备编号（套装效果可以按武器区分）
    # 道具符咒（只在这一次副本挑战里有效）：泣血符按造成伤害的百分比回血；连击符每次攻击有概率再攻击一次
    lifesteal_pct: int = 0
    combo_chance: int = 0


def _clamp_stat(rules: RuleSet, key: str, value: float) -> int | float:
    spec = rules.stats.get(key)
    if spec is not None:
        if spec.min is not None and value < spec.min:
            value = spec.min
        if spec.max is not None and value > spec.max:
            value = spec.max
    return to_number(value)


def _weapon_flags(damage_type: str, weapon_id: str = "") -> dict[str, Any]:
    flags: dict[str, Any] = {t: damage_type == t for t in DAMAGE_TYPES}
    try:
        flags["id"] = int(str(weapon_id).strip() or 0)
    except ValueError:
        flags["id"] = 0                     # 编号不是数字时，按武器区分的效果都不生效
    return flags


def _normalize_effects(effects: Iterable[str | tuple[str, int]]) -> tuple[tuple[str, int], ...]:
    merged: dict[str, int] = {}
    for item in effects:
        effect_id, pieces = (item, 1) if isinstance(item, str) else (item[0], int(item[1]))
        merged[effect_id] = max(merged.get(effect_id, 0), pieces)
    return tuple(merged.items())


def build_player(
    rules: RuleSet,
    *,
    level: int,
    base: Mapping[str, float],
    effects: Iterable[str | tuple[str, int]] = (),
    damage_type: str = "physical",
    name: str = "玩家",
    weapon_id: str = "",
) -> FighterSpec:
    """汇总玩家面板：基础属性（角色 + 装备的合计，百分比之前）→ 百分比加成 → 固定值加成（max 方式的只取最大）→ 上下限。

    与旧版 catalog.combat_stats_from_panel 的顺序一致：百分比按基础值计算，
    "获得（0.1*法力）敏捷"这类固定值加成用基础属性计算，加在百分比之后。
    """
    if damage_type not in DAMAGE_TYPES:
        raise ValueError(f"未知的伤害类型：{damage_type}")
    own = _normalize_effects(effects)
    # 基础属性在默认值上累加（暴击伤害默认 150%，装备上填的是额外暴击伤害）
    base_full = {key: spec.default for key, spec in rules.stats.items()}
    for key, value in base.items():
        base_full[key] = to_number(base_full.get(key, 0) + value)
    percent_stats: Mapping[str, str] = rules.setting("percent_stats", {}) or {}
    pct: dict[str, float] = {}
    flat: dict[str, float] = {}
    best: dict[tuple[str, str], float] = {}     # (属性, 组) → 取最大的加成
    muls: dict[str, list[float]] = {}
    sets: dict[str, float] = {}
    for pct_key, target in percent_stats.items():
        if base_full.get(pct_key):
            pct[target] = pct.get(target, 0) + base_full[pct_key]

    env_self = {"base": ZeroDict(base_full), "level": level}
    weapon = _weapon_flags(damage_type, weapon_id)
    active = [(rules.effects[e], 1) for e in rules.global_effects] + [(rules.effects[e], p) for e, p in own]
    for effect, pieces in active:
        env = {"self": env_self, "weapon": weapon, "pieces": pieces, **effect.params, FORMULAS_KEY: rules.formulas}
        for mod in effect.statics:
            if mod.cond is not None and not mod.cond(env):
                continue
            value = to_number(mod.value.number(env))
            if mod.op == "add":
                flat[mod.stat] = flat.get(mod.stat, 0) + value
            elif mod.op == "add_pct":
                pct[mod.stat] = pct.get(mod.stat, 0) + value
            elif mod.op == "max":
                key = (mod.stat, mod.group)
                best[key] = max(best.get(key, value), value)
            elif mod.op == "mul":
                muls.setdefault(mod.stat, []).append(value)
            elif mod.op == "set":
                sets[mod.stat] = value

    panel: dict[str, float] = {}
    for key in rules.stats:
        value = base_full.get(key, 0)
        if pct.get(key):
            value = value * (100 + pct[key]) // 100
        value += flat.get(key, 0) + sum(v for (stat, _), v in best.items() if stat == key)
        for m in muls.get(key, ()):
            value = value * m
        if key in sets:
            value = sets[key]
        panel[key] = _clamp_stat(rules, key, value)
    return FighterSpec(PLAYER, name, level, panel, base_full, own, damage_type, weapon_id=weapon_id)


def build_monster(rules: RuleSet, monster: MonsterDef) -> FighterSpec:
    """怪物面板直接来自规则库。怪物的 crit_dmg 填的是"额外暴击伤害"（与图鉴一致），这里加上默认的 150%。"""
    panel = {key: spec.default for key, spec in rules.stats.items()}
    panel["dodge"] = rules.setting("monster_default_dodge", 0)
    stats = {k: to_number(v) for k, v in monster.stats.items()}
    panel.update(stats)
    panel["crit_dmg"] = rules.setting("default_crit_dmg", 150) + stats.get("crit_dmg", 0)
    panel = {k: _clamp_stat(rules, k, v) for k, v in panel.items()}
    return FighterSpec(MONSTER, monster.name, monster.level, panel, dict(panel),
                       _normalize_effects(monster.effects))


def build_world_boss(rules: RuleSet, level: int) -> FighterSpec:
    """世界BOSS：生命极高，防御法抗为 0，必定先手，免疫负面层数，攻击每回合增长。"""
    conf = rules.setting("world_boss", {}) or {}
    panel = {key: spec.default for key, spec in rules.stats.items()}
    panel.update({"hp": conf.get("hp", 10**12), "atk": conf.get("atk", 50), "defense": 0, "agi": 0,
                  "magic_resist": 0, "dodge": 0, "crit": 0,
                  "crit_dmg": rules.setting("default_crit_dmg", 150)})
    return FighterSpec(MONSTER, "世界BOSS", level, panel, dict(panel), (), "physical", world_boss=True)


# ---------------------------------------------------------------- 战报


@dataclass
class Turn:
    round_no: int
    side: str                                   # 出手方
    damage: int = 0                             # 主攻击伤害
    total: int = 0                              # 这次出手造成的全部伤害（含效果追加）
    crit: bool = False
    dodged: bool = False
    absorbed: int = 0                           # 被护盾吸收的伤害
    player_hp: int = 0
    monster_hp: int = 0
    parts: list[tuple[str, int]] = field(default_factory=list)   # 效果追加的伤害：(名称, 数值)
    notes: list[str] = field(default_factory=list)


@dataclass
class BattleNote:
    round_no: int
    turn_index: int                           # 生成时已完成的出手数，0 起；保留回合结束/无出手时的位置
    phase: str
    side: str
    text: str


@dataclass
class BattleResult:
    won: bool
    timeout: bool
    draw: bool
    player_first: bool
    rounds: int
    player_hp: int
    monster_hp: int
    player_max_hp: int
    monster_max_hp: int
    turns: list[Turn]
    notes: list[str]
    carry: dict[str, Any]
    player_crits: int = 0
    player_dodges: int = 0
    monster_dodges: int = 0
    triggered: dict[str, int] = field(default_factory=dict)     # 每个效果触发了几次
    foe_stacks: dict[str, int] = field(default_factory=dict)    # 战斗结束时怪物身上的层数（沉沦印记结算奖励用）
    notes_timeline: list[BattleNote] = field(default_factory=list)


# ---------------------------------------------------------------- 战斗中的参战方


@dataclass
class _Mod:
    stat: str
    op: str
    value: float
    rounds: int | None
    effect: str                 # 来源效果的 id


@dataclass
class _Event:
    prevented: bool = False
    phase: str = ''


class _FighterView(Mapping):
    """表达式里的 self / foe：属性按当前状态实时计算。"""

    __slots__ = ("_f",)

    def __init__(self, fighter: "Fighter") -> None:
        self._f = fighter

    def __getitem__(self, key: str) -> Any:
        f = self._f
        if key in f.rules.stats:
            return f.stat(key)
        if key == "panel":
            return f.panel
        if key == "base":
            return f.base
        if key == "stacks":
            return f.stacks
        if key == "vars":
            return f.vars
        if key == "hp_now":
            return f.hp_now
        if key == "hp_max":
            return f.hp_max
        if key == "shield":
            return f.shield
        if key == "level":
            return f.level
        if key == "is_player":
            return f.side == PLAYER
        if key == "is_world_boss":
            return f.world_boss
        raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and (key in self._f.rules.stats or key in _VIEW_FIELDS)

    def __iter__(self) -> Iterator[str]:
        yield from self._f.rules.stats
        yield from _VIEW_FIELDS

    def __len__(self) -> int:
        return len(self._f.rules.stats) + len(_VIEW_FIELDS)


_VIEW_FIELDS = ("panel", "base", "stacks", "vars", "hp_now", "hp_max", "shield", "level",
                "is_player", "is_world_boss")


class Fighter:
    def __init__(self, battle: "Battle", spec: FighterSpec, hp: int | None) -> None:
        self.battle = battle
        self.rules = battle.rules
        self.spec = spec
        self.side = spec.side
        self.name = spec.name
        self.level = spec.level
        self.damage_type = spec.damage_type
        self.world_boss = spec.world_boss
        self.panel: dict[str, float] = dict(spec.panel)
        self.base = ZeroDict(spec.base)
        self.hp_max = int(self.panel.get("hp", 1))
        self.start_full = hp is None
        self.hp_now = self.hp_max if hp is None else max(0, min(self.hp_max, int(hp)))
        self.shield = 0
        self.stacks = ZeroDict()
        self.vars = ZeroDict()
        self.carry_keys: set[str] = set()
        self.once_battle: set[str] = set()
        self.once_run: set[str] = set()
        self.cooldowns: dict[str, int] = {}
        self.mods: list[_Mod] = []
        self.weapon = _weapon_flags(spec.damage_type, spec.weapon_id)
        self.view = _FighterView(self)
        self.foe: Fighter = self  # 由 Battle 设置
        self._cache: dict[str, float] = {}
        self._cache_version = -1
        self._computing: set[str] = set()
        effects: list[tuple[Effect, int]] = [(self.rules.effects[e], 1) for e in self.rules.global_effects]
        effects += [(self.rules.effects[e], p) for e, p in spec.effects]
        self.effects = effects
        self.handlers: dict[str, list[tuple[Effect, int, Trigger]]] = {}
        for effect, pieces in effects:
            for trigger in effect.triggers:
                self.handlers.setdefault(trigger.on, []).append((effect, pieces, trigger))

    @property
    def dead(self) -> bool:
        return self.hp_now <= 0

    # ---- 属性

    def stat(self, key: str, skip: frozenset[str] = frozenset()) -> int | float:
        """当前属性。skip：不计入这些效果（id）给的加成和降低（不走缓存）。"""
        if skip:
            return self._compute(key, skip)
        battle = self.battle
        if self._cache_version != battle.version:
            self._cache.clear()
            self._cache_version = battle.version
        if key in self._cache:
            return self._cache[key]
        if key in self._computing:      # 加成的数值又用到了自己，取面板值，避免无限递归
            return self.panel.get(key, 0)
        self._computing.add(key)
        try:
            value = self._compute(key)
        finally:
            self._computing.discard(key)
        self._cache[key] = value
        return value

    def _compute(self, key: str, skip: frozenset[str] = frozenset()) -> int | float:
        x = self.panel.get(key, 0)
        add = 0
        flat_down = 0
        pct_down = 0
        reduce = False
        each: list[float] = []
        muls: list[float] = []

        def route(op: str, value: float) -> None:
            nonlocal add, flat_down, pct_down, reduce
            if op == "add":
                add += value
            elif op == "add_base_pct":
                add += self.base[key] * value // 100
            elif op == "down":
                flat_down += value
                reduce = True
            elif op == "down_pct":
                pct_down += value
                reduce = True
            elif op == "down_pct_each":
                each.append(value)
            elif op == "mul_pct":
                muls.append(value)

        for mod in self.mods:
            if mod.stat == key and mod.effect not in skip:
                route(mod.op, mod.value)
        for owner, effect, aura in self.battle.auras_on(self, key):
            if effect.id in skip:
                continue
            env = owner.env(effect)
            if aura.cond is not None and not aura.cond(env):
                continue
            value = to_number(aura.value.number(env))
            if value:
                route(aura.op, value)
        x = x + add
        if reduce:
            x = max(0, x - max(0, flat_down)) * (100 - min(100, max(0, pct_down))) // 100
        for v in each:
            x = x * (100 - min(100, max(0, v))) // 100
        for v in muls:
            x = x * (100 + v) // 100
        return _clamp_stat(self.rules, key, x)

    def add_mod(self, stat: str, op: str, value: float, rounds: int | None, effect: str) -> None:
        self.mods.append(_Mod(stat, op, value, rounds, effect))
        self.battle.touch()

    def change_panel(self, stat: str, op: str, value: float) -> None:
        old = self.panel.get(stat, 0)
        if op == "add":
            new = old + value
        elif op == "mul":
            new = old * value
        else:
            new = value
        self.panel[stat] = _clamp_stat(self.rules, stat, new)
        if stat == "hp":
            self.hp_max = int(self.panel["hp"])
            # 开场满血时，最大生命变了当前生命跟着变（与旧版开战前翻倍属性一致）
            self.hp_now = self.hp_max if self.start_full else min(self.hp_now, self.hp_max)
        self.battle.touch()

    def tick_round(self) -> None:
        kept: list[_Mod] = []
        for mod in self.mods:
            if mod.rounds is not None:
                mod.rounds -= 1
                if mod.rounds <= 0:
                    continue
            kept.append(mod)
        if len(kept) != len(self.mods):
            self.mods = kept
            self.battle.touch()
        for key in list(self.cooldowns):
            self.cooldowns[key] -= 1
            if self.cooldowns[key] <= 0:
                del self.cooldowns[key]

    # ---- 表达式环境

    def env(self, effect: Effect, pieces: int = 1, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
        env: dict[str, Any] = {
            "self": self.view, "foe": self.foe.view, "round_no": self.battle.round_no,
            "entry": self.battle.entry, "weapon": self.weapon, "pieces": pieces,
            FORMULAS_KEY: self.battle.rules.formulas,
        }
        env.update(effect.params)
        if extra:
            env.update(extra)
        return env


# ---------------------------------------------------------------- 主攻击


@dataclass
class _Hit:
    damage: int = 0
    crit: bool = False
    dodged: bool = False
    kind: str = "physical"
    absorbed: int = 0
    pen: int = 0                # 这次攻击的物理穿透（追加的物理伤害沿用）
    pen_pct: int = 0
    extra: int = 0              # 效果追加的物理/法术伤害（和主攻击一起吃增伤）
    true_raw: int = 0           # 效果追加的真实伤害（先加总，最后统一结算一次）
    segments: list[tuple[str, int]] | None = None   # 普通攻击被换成的各段（种类, 数值）；None 表示没换
    saved: bool = False         # 这次致命伤害被免疫了
    multi: bool = False         # 多段攻击（每段单独判定闪避、暴击，每段可单独提升伤害）
    true_part: int = 0          # 结算后的伤害里真实伤害的部分（提升伤害时不算这部分）
    precision_crit_dmg: int = 0 # 精准武器这次额外的暴击伤害%（追击要还原暴击前的伤害）
    source: str = ""            # 换掉普通攻击的效果 id

    def env(self) -> "_HitView":
        return _HitView(self)


class _HitView(Mapping):
    """表达式里的 hit：读的是这次攻击当前的值（前面的效果改过伤害，后面的效果看到的就是改过的）。"""

    __slots__ = ("_h",)
    _KEYS = ("damage", "crit", "dodged", "saved", "multi", "true_part", "precision_crit_dmg",
             "magic", "physical", "precision", "by")

    def __init__(self, hit: _Hit) -> None:
        self._h = hit

    def __getitem__(self, key: str) -> Any:
        h = self._h
        if key in ("magic", "physical", "precision"):
            return h.kind == key
        if key == "by":
            return ZeroDict({h.source: 1} if h.source else {})
        if key in self._KEYS:
            return getattr(h, key)
        raise KeyError(key)

    def __iter__(self):
        return iter(self._KEYS)

    def __len__(self) -> int:
        return len(self._KEYS)


class Battle:
    def __init__(
        self,
        rules: RuleSet,
        player: FighterSpec,
        monster: FighterSpec,
        *,
        rng: Rng,
        hp: int | None = None,
        carry: Mapping[str, Any] | None = None,
        entry: bool = True,
        max_rounds: int | None = 50,
    ) -> None:
        self.rules = rules
        self.rng = rng
        self.version = 0
        self.round_no = 0
        self.entry = entry
        self.max_rounds = max_rounds
        self.actions_run = 0
        self.depth = 0
        self.turns: list[Turn] = []
        self.notes: list[str] = []
        self.notes_timeline: list[BattleNote] = []
        self.triggered: dict[str, int] = {}
        self.pending: dict[str, list[tuple[str, int]]] = {PLAYER: [], MONSTER: []}
        self.current_turn: Turn | None = None
        self.player = Fighter(self, player, hp)
        self.monster = Fighter(self, monster, None)
        self.player.foe, self.monster.foe = self.monster, self.player
        if carry and not entry:
            for key, value in (carry.get("vars") or {}).items():
                self.player.vars[key] = value
                self.player.carry_keys.add(key)
            self.player.once_run = set(carry.get("once_run") or ())
        self._auras: dict[tuple[str, str], list[tuple[Fighter, Effect, Any]]] = {}
        for owner in (self.player, self.monster):
            for effect, _pieces in owner.effects:
                for aura in effect.auras:
                    target = owner if aura.target == "self" else owner.foe
                    self._auras.setdefault((target.side, aura.stat), []).append((owner, effect, aura))

    # ---- 状态

    def touch(self) -> None:
        self.version += 1

    def auras_on(self, fighter: Fighter, key: str) -> list[tuple[Fighter, Effect, Any]]:
        return self._auras.get((fighter.side, key), [])

    def f(self, name: str, **values: Any) -> int | float:
        return self.rules.formulas[name](**values)

    def deal(self, target: Fighter, amount: int, label: str | None = None, source: Fighter | None = None) -> int:
        amount = max(0, int(amount))
        if amount:
            target.hp_now = max(0, target.hp_now - amount)
            self.touch()
        if label is not None and source is not None:
            if self.current_turn is not None and self.current_turn.side == source.side:
                self.current_turn.parts.append((label, amount))
                self.current_turn.total += amount
            else:
                self.pending[source.side].append((label, amount))
        return amount

    # ---- 触发

    def fire(self, event: str, owners: Iterable[Fighter], extra: Mapping[str, Any] | None = None,
             stack: str | None = None) -> _Event:
        self.depth += 1
        try:
            if self.depth > MAX_DEPTH:
                raise BattleError(f"效果互相触发超过 {MAX_DEPTH} 层，规则可能写成了死循环（时机：{event}）")
            return self._fire(event, owners, extra, stack)
        finally:
            self.depth -= 1

    def _fire(self, event: str, owners: Iterable[Fighter], extra: Mapping[str, Any] | None,
              stack: str | None) -> _Event:
        ev = _Event(phase=event)
        queue: list[tuple[int, int, Fighter, Effect, int, Trigger]] = []
        order = 0
        for owner in owners:
            for effect, pieces, trigger in owner.handlers.get(event, ()):
                queue.append((trigger.priority, order, owner, effect, pieces, trigger))
                order += 1
        queue.sort(key=lambda item: (item[0], item[1]))
        for _, _, owner, effect, pieces, trigger in queue:
            if ev.prevented:
                break
            if trigger.stack is not None and trigger.stack != stack:
                continue
            if trigger.once == "battle" and trigger.key in owner.once_battle:
                continue
            if trigger.once == "run" and trigger.key in owner.once_run:
                continue
            if trigger.key in owner.cooldowns:
                continue
            env = owner.env(effect, pieces, extra)
            if trigger.cond is not None and not trigger.cond(env):
                continue
            if trigger.chance is not None and not self.rng.roll(to_number(trigger.chance.number(env))):
                continue
            if trigger.once == "battle":
                owner.once_battle.add(trigger.key)
            elif trigger.once == "run":
                owner.once_run.add(trigger.key)
            if trigger.cooldown:
                owner.cooldowns[trigger.key] = trigger.cooldown
            name = effect.name
            self.triggered[name] = self.triggered.get(name, 0) + 1
            self.run_actions(owner, effect, trigger.actions, env, ev)
        return ev

    def run_actions(self, owner: Fighter, effect: Effect, actions: Iterable[Action],
                    env: dict[str, Any], ev: _Event) -> None:
        last = {"prevented": False, "count": 0}
        env["last"] = last
        for action in actions:
            self.actions_run += 1
            if self.actions_run > MAX_ACTIONS:
                raise BattleError(f"一场战斗执行的动作超过 {MAX_ACTIONS} 个，规则可能写成了死循环（{effect.name}）")
            if action.cond is not None and not action.cond(env):
                continue
            getattr(self, f"_act_{action.kind}")(owner, effect, action, env, ev, last)

    # ---- 动作

    def _value(self, action: Action, key: str, env: Mapping[str, Any]) -> int | float:
        return to_number(action.exprs[key].number(env))

    def _target(self, owner: Fighter, action: Action, default: str) -> Fighter:
        return owner if action.args.get("target", default) == "self" else owner.foe

    def _act_modify_stat(self, owner, effect, action, env, ev, last) -> None:
        target = self._target(owner, action, "self")
        stat = action.args["stat"]
        value = self._value(action, "value", env)
        if action.args.get("scope", "battle") == "panel":
            target.change_panel(stat, action.args["op"], value)
            return
        rounds = int(self._value(action, "rounds", env)) if "rounds" in action.exprs else None
        if rounds is not None and rounds <= 0:
            return
        target.add_mod(stat, action.args.get("op", "add"), value, rounds, effect.id)

    def _act_damage(self, owner, effect, action, env, ev, last) -> None:
        target = self._target(owner, action, "foe")
        ignore = {key: int(self._value(action, key, env)) for key in ("ignore_def", "ignore_resist")
                  if key in action.exprs}
        crit = {key: self._value(action, key, env) for key in ("crit_rate", "crit_dmg") if key in action.exprs}
        amount = self.effect_damage(owner, target, action.args["kind"], self._value(action, "value", env),
                                    pen=bool(action.args.get("pen")), can_crit=bool(action.args.get("can_crit")),
                                    bonus=bool(action.args.get("bonus")),
                                    skip=frozenset(action.args.get("not_lowered_by") or ()),
                                    base_def=bool(action.args.get("base_def")), **ignore, **crit)
        amount = self.deal(target, amount, str(action.args.get("label") or effect.name), owner)
        last["damage"] = amount
        if amount > 0 and target is owner.foe:
            self.fire("dealt_damage", [owner], {"hit": ZeroDict(), "dealt": {"amount": amount, "attack": False,
                                                          "by": ZeroDict({effect.id: 1})}})

    def _act_replace_hit(self, owner, effect, action, env, ev, last) -> None:
        hit: _Hit | None = env.get("_hit")
        if hit is None or hit.segments is not None:
            return          # 已经被优先级更高的效果换过了
        hit.segments = [(seg["kind"], int(to_number(action.exprs[f"hits.{i}"].number(env))))
                        for i, seg in enumerate(action.args["hits"])]
        multi = action.args.get("multi")
        hit.multi = bool(multi) if multi is not None else len(hit.segments) > 1
        hit.source = effect.id

    def _act_scale_hit(self, owner, effect, action, env, ev, last) -> None:
        """伤害 × value ÷ base（base 默认 100）。with_true：连真实伤害一起提升；at_least_1：结果至少 1。"""
        pct = int(self._value(action, "value", env))
        base = int(self._value(action, "base", env)) if "base" in action.exprs else 100
        floor_one = bool(action.args.get("at_least_1"))

        def scaled(value: int) -> int:
            if value <= 0:
                return value
            out = value * pct // base
            return max(1, out) if floor_one else out

        seg: dict | None = env.get("_seg")
        if seg is not None:             # 多段攻击的这一段
            seg["damage"] = scaled(seg["damage"])
            return
        hit: _Hit | None = env.get("_hit")
        if hit is None:
            return
        if action.args.get("with_true"):
            hit.damage = scaled(hit.damage)
        else:                           # 这次攻击（真实伤害不提升）
            rest = max(0, hit.damage - hit.true_part)
            hit.damage = scaled(rest) + hit.true_part

    def _act_chase(self, owner, effect, action, env, ev, last) -> None:
        """追击：第 n 次追击的比例 = pct − decay × 本回合已追击次数（记在 counter 标记里），降到 0 就停；
        每段单独判定暴击，暴击了就再追击一次。每段触发"每一段命中后"（seg.chase 为真）。"""
        counter = action.args["counter"]
        base = int(self._value(action, "base", env))
        start, decay = int(self._value(action, "pct", env)), int(self._value(action, "decay", env))
        fallback = self.rules.setting("default_crit_dmg", 150)
        hit: _Hit | None = env.get("_hit")
        total = count = 0
        pending = 1
        while pending > 0 and count < 1000:
            pending -= 1
            mult = max(0, start - decay * int(to_number(owner.vars.get(counter, 0))))
            if mult <= 0:
                continue
            owner.vars[counter] = int(to_number(owner.vars.get(counter, 0))) + 1
            self.touch()
            count += 1
            seg_damage = base * mult // 100
            if self.rng.roll(self._value(action, "crit_rate", env)):
                seg_damage = int(self.f("crit_hit", value=seg_damage, mult=self._value(action, "crit_dmg", env),
                                        fallback=fallback))
                pending += 1
            seg = {"damage": seg_damage}
            self.fire("segment", [owner], {"hit": hit.env() if hit else ZeroDict(), "_seg": seg,
                                           "seg": {"damage": seg_damage, "kind_magic": False, "chase": True}})
            total += seg["damage"]
        last["count"] = count
        if total <= 0:
            return
        if hit is not None:             # 并进这次攻击一起结算
            hit.damage += total
        else:
            self.deal(owner.foe, total, str(action.args.get("label") or effect.name), owner)

    def _act_lose_hp(self, owner, effect, action, env, ev, last) -> None:
        amount = int(self._value(action, "value", env))
        if amount > 0 and owner.hp_now > 1:
            owner.hp_now = max(1, owner.hp_now - amount)
            self.touch()

    def _act_execute(self, owner, effect, action, env, ev, last) -> None:
        target = self._target(owner, action, "foe")
        if target.hp_now > 0:
            self.deal(target, target.hp_now, str(action.args.get("label") or effect.name), owner)

    def _act_reduce_hit(self, owner, effect, action, env, ev, last) -> None:
        hit: _Hit | None = env.get("_hit")
        amount = int(self._value(action, "value", env))
        if hit is not None and amount > 0 and hit.damage > 0:
            hit.damage = max(0, hit.damage - amount)

    def _act_set_hit(self, owner, effect, action, env, ev, last) -> None:
        hit: _Hit | None = env.get("_hit")
        if hit is None:
            return
        value = self._value(action, "value", env)
        part = action.args["part"]
        if part == "true":
            hit.true_raw += max(0, int(value))
        elif part == "physical":
            amount = self.physical(owner, owner.foe, value, pen=hit.pen, pen_pct=hit.pen_pct)
            hit.extra += self._scale_monster(owner, owner.foe, amount)
        else:
            amount = self.magic(owner, owner.foe, value)
            hit.extra += self._scale_monster(owner, owner.foe, amount)

    def _act_heal(self, owner, effect, action, env, ev, last) -> None:
        target = self._target(owner, action, "self")
        value = max(0, int(self._value(action, "value", env)))
        if value and target.hp_now > 0:
            target.hp_now = min(target.hp_max, target.hp_now + value)
            self.touch()

    def _act_shield(self, owner, effect, action, env, ev, last) -> None:
        target = self._target(owner, action, "self")
        value = max(0, int(self._value(action, "value", env)))
        if value:
            target.shield += value
            self.touch()

    def _act_stack(self, owner, effect, action, env, ev, last) -> None:
        name = action.args["name"]
        spec = self.rules.stacks[name]
        holder = self._target(owner, action, spec.owner)
        op = action.args.get("op", "add")
        if op == "clear":
            if holder.stacks[name]:
                holder.stacks[name] = 0
                self.touch()
            last["prevented"] = False
            return
        value = int(self._value(action, "value", env))
        if op == "add":
            last["prevented"] = self.add_stack(owner, holder, name, value)
            return
        current = holder.stacks[name]
        new = max(0, current - value) if op == "remove" else max(0, value)
        if new > current and holder.world_boss and spec.boss_immune:
            last["prevented"] = False
            return
        cap = self.stack_cap(owner, spec)
        if cap is not None:
            new = min(cap, new)
        if new != current:
            holder.stacks[name] = new
            self.touch()
        last["prevented"] = False

    def stack_cap(self, applier: Fighter, spec) -> int | None:
        """层数上限：写了 max_stat 且施加者这个属性大于 0 时用它，否则用 max。"""
        if spec.max_stat:
            raised = int(applier.stat(spec.max_stat))
            if raised > 0:
                return raised
        return spec.max

    def add_stack(self, applier: Fighter, holder: Fighter, name: str, amount: int) -> bool:
        """叠层。返回 True 表示这次叠层被"层数即将叠满"时机里的效果取消了。"""
        spec = self.rules.stacks[name]
        if amount <= 0 or (holder.world_boss and spec.boss_immune):
            return False
        current = holder.stacks[name]
        cap = self.stack_cap(applier, spec)
        info = {"count": current, "adding": amount, "max": cap or 0}
        if cap is not None and current + amount >= cap:
            if self.fire("stack_full", [applier], {"stack": info}, stack=name).prevented:
                return True
        new = current + amount
        if cap is not None:
            new = min(cap, new)
        holder.stacks[name] = new
        self.touch()
        if self.current_turn is not None:
            self.current_turn.notes.append(f"{spec.name}{new}层")
        self.fire("stack_gain", [applier], {"stack": {"count": new, "adding": amount, "max": cap or 0}}, stack=name)
        return False

    def _act_prevent(self, owner, effect, action, env, ev, last) -> None:
        ev.prevented = True

    def _act_flag(self, owner, effect, action, env, ev, last) -> None:
        name = action.args["name"]
        owner.vars[name] = self._value(action, "value", env)
        if action.kind == "carry" or action.args.get("carry"):
            owner.carry_keys.add(name)
        self.touch()

    _act_carry = _act_flag

    def _record_note(self, owner: Fighter, text: str, ev: _Event) -> None:
        if self.current_turn is not None:
            self.current_turn.notes.append(text)
        elif self.round_no == 0 and ev.phase != 'battle_end':
            self.notes.append(text)
        else:
            self.notes_timeline.append(BattleNote(self.round_no, len(self.turns), ev.phase, owner.side, text))

    def _act_note(self, owner, effect, action, env, ev, last) -> None:
        text = str(action.args["text"])
        for key, value in effect.params.items():
            text = text.replace("{" + key + "}", str(value))
        self._record_note(owner, text, ev)

    def _act_random(self, owner, effect, action, env, ev, last) -> None:
        count = int(action.args.get("_weighted") or 0)
        weights = [max(0, int(to_number(action.exprs[f"weight.{j}"].number(env)))) for j in range(count)]
        if weights and sum(weights) > 0:
            # 写了权重：掷 0 到（权重合计 - 1）的整数，落在哪一段选哪个（与旧版的掷点方式一致）
            roll, acc, chosen = self.rng.randrange(int(sum(weights))), 0, len(weights) - 1
            for i, weight in enumerate(weights):
                acc += weight
                if roll < acc:
                    chosen = i
                    break
            label, actions = action.choices[chosen]
        else:
            label, actions = self.rng.choice(action.choices)
        self._record_note(owner, f"{effect.name}：{label}", ev)
        self.run_actions(owner, effect, actions, env, ev)

    # ---- 伤害计算（每一步都是规则里的公式）

    def _levels(self, attacker: Fighter, defender: Fighter) -> tuple[int, int]:
        """返回 (玩家等级, 祝福后参与计算的怪物等级)。"""
        player = attacker if attacker.side == PLAYER else defender
        monster = defender if attacker.side == PLAYER else attacker
        eff = self.f("effective_level", level=player.level, foe_level=monster.level,
                     bless=player.stat("bless_level"))
        return player.level, eff

    def _coef(self, attacker: Fighter, defender: Fighter) -> float:
        """玩家打怪物：怪物等级高时伤害降低；怪物打玩家不在这里算（见 _scale_monster）。"""
        if attacker.side != PLAYER:
            return 1.0
        level, eff = self._levels(attacker, defender)
        return self.f("level_coef_taken", level=level, foe_level=eff)

    def _scale_monster(self, attacker: Fighter, defender: Fighter, value: int) -> int:
        if attacker.side == PLAYER:
            return value
        level, eff = self._levels(attacker, defender)
        boost = self.f("level_coef_dealt", level=level, foe_level=eff)
        return int(self.f("scale_dealt", value=value, coef=boost))

    def physical(self, attacker: Fighter, defender: Fighter, value: float, *, pen: int = 0,
                 pen_pct: int = 0, reduce: float | None = None, skip: frozenset[str] = frozenset(),
                 base_def: bool = False) -> int:
        defense = defender.panel.get("defense", 0) if base_def else defender.stat("defense", skip)
        if attacker.side == PLAYER:
            pen_pct += attacker.stat("extra_ignore_def_pct")    # 对全部物理伤害生效的无视防御（幸运三角）
        eff_def = self.f("def_after_pen", defense=defense, pen=pen, pen_pct=pen_pct)
        mitigation = self.f("physical_mitigation", defense=eff_def, level=attacker.level)
        damage = self.f("physical_damage", atk=value, mitigation=mitigation,
                        coef=self._coef(attacker, defender),
                        reduce=defender.stat("dmg_reduce") if reduce is None else reduce)
        return int(damage)

    def magic(self, attacker: Fighter, defender: Fighter, value: float, *,
              pen: int | None = None, pen_pct: int | None = None, skip: frozenset[str] = frozenset()) -> int:
        """玩家造成的法术伤害都再加上"额外无视法抗"（幸运三角）；结果再乘目标"受到的法术伤害提升"（腐朽）。"""
        if pen_pct is None:
            pen_pct = attacker.stat("ignore_resist_pct") + attacker.stat("ignore_def_pct")
        if attacker.side == PLAYER:
            pen_pct += attacker.stat("extra_ignore_resist_pct")
        resist = self.f("resist_after_pen", resist=defender.stat("magic_resist", skip),
                        pen=attacker.stat("ignore_magic_resist") if pen is None else pen, pen_pct=pen_pct)
        damage = int(self.f("level_reduce", value=int(value) - resist, coef=self._coef(attacker, defender),
                            reduce=defender.stat("dmg_reduce")))
        return int(self.f("amplify", value=damage, pct=defender.stat("magic_taken_pct")))

    def _hit_mul(self, attacker: Fighter, value: int) -> int:
        """单独相乘的增伤（幸运三角）：玩家造成的全部伤害（真实伤害除外）在增伤之前单独乘一次。"""
        pct = attacker.stat("extra_dmg_mul_pct")
        return value * (100 + pct) // 100 if pct and value > 0 else value

    def true_damage(self, attacker: Fighter, defender: Fighter, value: float) -> int:
        return int(self.f("level_reduce", value=value, coef=self._coef(attacker, defender),
                          reduce=defender.stat("dmg_reduce")))

    def effect_damage(self, attacker: Fighter, defender: Fighter, kind: str, value: float, *,
                      pen: bool = False, can_crit: bool = False, bonus: bool = False,
                      ignore_def: int | None = None, ignore_resist: int | None = None,
                      skip: frozenset[str] = frozenset(), crit_rate: float | None = None,
                      crit_dmg: float | None = None, base_def: bool = False) -> int:
        """效果追加的一段伤害。默认不吃穿透、不暴击、不吃增伤（与旧版的额外伤害一致）。
        写了 ignore_def / ignore_resist 时只按这个百分比无视防御/法抗，不用自己的穿透。
        skip：算目标防御/法抗时不计入这些效果（id）造成的降低。"""
        if kind == "physical":
            if ignore_def is not None:
                amount = self.physical(attacker, defender, value, pen=0, pen_pct=ignore_def, skip=skip)
            else:
                amount = self.physical(
                    attacker, defender, value,
                    pen=attacker.stat("penetration") if pen else 0,
                    pen_pct=attacker.stat("pen_pct") + attacker.stat("ignore_def_pct") if pen else 0, skip=skip,
                    base_def=base_def)
        elif kind == "magic":
            if ignore_resist is not None:
                amount = self.magic(attacker, defender, value, pen=0, pen_pct=ignore_resist, skip=skip)
            else:
                amount = self.magic(attacker, defender, value, skip=skip)
        else:
            amount = self.true_damage(attacker, defender, value)
        amount = self._scale_monster(attacker, defender, amount)
        if kind != "true":
            amount = self._hit_mul(attacker, amount)
        rate = attacker.stat("crit") if crit_rate is None else crit_rate
        if can_crit and amount > 0 and self.rng.roll(rate):
            amount = int(self.f("crit_hit", value=amount,
                                mult=attacker.stat("crit_dmg") if crit_dmg is None else crit_dmg,
                                fallback=self.rules.setting("default_crit_dmg", 150)))
        if bonus and kind != "true":
            amount = int(self.f("amplify", value=amount, pct=attacker.stat("dmg_pct")))
        return amount

    def main_hit(self, attacker: Fighter, defender: Fighter) -> _Hit:
        if attacker.side == PLAYER:
            return self._player_hit(attacker, defender)
        return self._monster_hit(attacker, defender)

    def _player_hit(self, att: Fighter, dfn: Fighter) -> _Hit:
        kind = att.damage_type
        fallback = self.rules.setting("default_crit_dmg", 150)
        hit = _Hit(kind=kind)
        # 效果可以把这次普通攻击换成指定的一段或多段攻击（多个效果都换时，优先级小的生效）；
        # 这里结算的效果（天鸣守望起爆、幸运三角判定）在读这次攻击的属性之前
        self.fire("attack", [att], {"hit": hit.env(), "_hit": hit})
        pen = att.stat("penetration")
        pen_pct = att.stat("pen_pct") + att.stat("ignore_def_pct")
        crit_rate = att.stat("magic_crit_rate") if kind == "magic" else att.stat("crit")
        crit_dmg = fallback if kind == "magic" else att.stat("crit_dmg")
        if kind == "precision" and not dfn.world_boss:
            agi, foe_agi = att.stat("agi"), dfn.stat("agi")
            pen += self.f("precision_flat_pen", agi=agi, foe_agi=foe_agi)
            pen_pct += self.f("precision_pen_pct", agi=agi, foe_agi=foe_agi)
            crit_rate += self.f("precision_crit", agi=agi, foe_agi=foe_agi)
            bonus_cd = self.f("precision_crit_dmg", agi=agi, foe_agi=foe_agi)
            crit_dmg += bonus_cd
        else:
            bonus_cd = 0
        hit.pen, hit.pen_pct, hit.precision_crit_dmg = pen, pen_pct, int(bonus_cd)
        if hit.segments is None:
            if kind == "magic":
                base = self.magic(att, dfn, att.stat("mp"))
            else:
                base = self.physical(att, dfn, att.stat("atk"), pen=pen, pen_pct=pen_pct)
            self._land(att, dfn, hit, base, crit_rate, crit_dmg, fallback)
        elif not hit.multi:
            (seg_kind, value), = hit.segments[:1] or [(kind, 0)]
            self._one_segment(att, dfn, hit, seg_kind, value, crit_rate, crit_dmg, fallback)
        else:
            self._segments(att, dfn, hit, crit_rate, crit_dmg, fallback)
        # 效果给这次攻击追加的伤害：物理/法术并进主攻击一起吃增伤，真实伤害加总后统一结算一次
        self.fire("compute_hit", [att], {"hit": hit.env(), "_hit": hit})
        true = self.true_damage(att, dfn, hit.true_raw) if hit.true_raw > 0 else 0
        true = self._scale_monster(att, dfn, true)
        rest = 0 if hit.dodged else hit.damage + hit.extra
        down = att.stat("dmg_dealt_down")
        if down:
            # 造成伤害降低：按合计伤害打折，折掉的部分算在非真实伤害上（被闪避时只剩真实伤害）
            total = int(self.f("lessen", value=rest + true, pct=down))
            if hit.dodged:
                true = total
            else:
                rest = max(0, total - true)
        rest = self._hit_mul(att, rest)
        hit.damage = int(self.f("amplify", value=rest, pct=att.stat("dmg_pct"))) + true
        hit.true_part = true
        return hit

    def _land(self, att: Fighter, dfn: Fighter, hit: _Hit, base: int, crit_rate, crit_dmg, fallback,
              *, add: bool = True) -> tuple[bool, int]:
        """一段攻击：先判定闪避，再判定暴击。返回（这段是否被闪避，这段的伤害）。"""
        if self.rng.roll(dfn.stat("dodge")):
            hit.dodged = True
            return True, 0
        if base > 0:
            if self.rng.roll(crit_rate):
                hit.crit = True
                base = int(self.f("crit_hit", value=base, mult=crit_dmg, fallback=fallback))
            if add:
                hit.damage += base
            return False, base
        return False, 0

    def _one_segment(self, att: Fighter, dfn: Fighter, hit: _Hit, seg_kind: str, value: int,
                     crit_rate, crit_dmg, fallback) -> int:
        """换过的普通攻击（单段）：和普通攻击一样结算，只是数值换了。"""
        if seg_kind == "true":
            hit.true_raw += max(0, value)
            return 0
        if seg_kind == "magic":
            base = self.magic(att, dfn, value)
            crit_rate, crit_dmg = att.stat("magic_crit_rate"), fallback
        else:
            base = self.physical(att, dfn, value, pen=hit.pen, pen_pct=hit.pen_pct)
        return self._land(att, dfn, hit, base, crit_rate, crit_dmg, fallback)[1]

    def _segments(self, att: Fighter, dfn: Fighter, hit: _Hit, crit_rate, crit_dmg, fallback) -> None:
        """换过的普通攻击：每段单独判定闪避和暴击，每段按当时的防御结算。
        全部段都被闪避才算这次攻击被闪避（与旧版一致：数值不大于 0 的段跳过，不算命中）。"""
        all_dodged = True
        for seg_kind, value in hit.segments:
            if value <= 0:
                continue
            if seg_kind == "true":
                hit.true_raw += value
                all_dodged = False
                continue
            if seg_kind == "magic":
                base = self.magic(att, dfn, value)
                rate, mult = att.stat("magic_crit_rate"), fallback
            else:
                base = self.physical(att, dfn, value, pen=hit.pen, pen_pct=hit.pen_pct)
                rate, mult = crit_rate, crit_dmg
            dodged, dealt = self._land(att, dfn, hit, base, rate, mult, fallback, add=False)
            if not dodged:
                all_dodged = False
            if dealt > 0:
                # 每一段命中后：效果可以提升这一段的伤害（真实伤害段不算）
                seg = {"damage": dealt, "crit": hit.crit, "kind": seg_kind}
                self.fire("segment", [att], {"hit": hit.env(), "_seg": seg,
                                              "seg": {"damage": dealt, "kind_magic": seg_kind == "magic",
                                                      "chase": False}})
                dealt = seg["damage"]
            hit.damage += dealt
        hit.dodged = all_dodged
        if all_dodged:
            hit.damage = 0

    def _monster_hit(self, att: Fighter, dfn: Fighter) -> _Hit:
        atk = att.stat("atk")
        if att.world_boss:
            conf = self.rules.setting("world_boss", {}) or {}
            atk = self.f("world_boss_atk", atk=atk, round_no=self.round_no, growth=conf.get("atk_growth_pct", 5))
        hit = _Hit(kind="physical")
        if self.rng.roll(dfn.stat("dodge")):
            hit.dodged = True
            return hit
        pen, pen_pct = att.stat("penetration"), att.stat("pen_pct")
        mit_raw = self.f("physical_mitigation",
                         defense=self.f("def_after_pen", defense=0, pen=pen, pen_pct=pen_pct), level=att.level)
        mit = self.f("physical_mitigation",
                     defense=self.f("def_after_pen", defense=dfn.stat("defense"), pen=pen, pen_pct=pen_pct),
                     level=att.level)
        raw = int(self.f("physical_damage", atk=atk, mitigation=mit_raw, coef=1.0, reduce=0))
        mitigated = int(self.f("physical_damage", atk=atk, mitigation=mit, coef=1.0, reduce=dfn.stat("dmg_reduce")))
        raw = self._scale_monster(att, dfn, raw)
        mitigated = self._scale_monster(att, dfn, mitigated)
        lessen = dfn.stat("dmg_taken_down")
        if lessen:
            raw = int(self.f("lessen", value=raw, pct=lessen))
            mitigated = int(self.f("lessen", value=mitigated, pct=lessen))
        if self.rng.roll(att.stat("crit")):
            hit.crit = True
            mult, fallback = att.stat("crit_dmg"), self.rules.setting("default_crit_dmg", 150)
            if raw > 0:
                raw = int(self.f("crit_hit", value=raw, mult=mult, fallback=fallback))
            if mitigated > 0:
                mitigated = int(self.f("crit_hit", value=mitigated, mult=mult, fallback=fallback))
        taken = dfn.stat("dmg_taken_pct")
        if taken:
            raw = int(self.f("amplify", value=raw, pct=taken))
            mitigated = int(self.f("amplify", value=mitigated, pct=taken))
        # 护盾按原始伤害吸收，打穿后按比例漏过减伤后的伤害
        if dfn.shield <= 0:
            hit.damage = mitigated
        elif raw <= 0:
            hit.damage = 0
        elif raw <= dfn.shield:
            dfn.shield -= raw
            hit.absorbed = raw
            self.touch()
        else:
            hit.absorbed = dfn.shield
            overflow = raw - dfn.shield
            dfn.shield = 0
            hit.damage = int(self.f("shield_overflow", mitigated=mitigated, overflow=overflow, raw=raw))
            self.touch()
        return hit

    # ---- 出手

    def attack(self, att: Fighter, dfn: Fighter) -> bool:
        """一次出手。返回 True 表示战斗结束（有一方倒下）。"""
        if dfn.dead:
            return True
        turn = Turn(self.round_no, att.side)
        turn.parts.extend(self.pending[att.side])
        turn.total += sum(v for _, v in self.pending[att.side])
        self.pending[att.side] = []
        self.current_turn = turn
        self.fire("before_action", [att])
        if dfn.dead:
            self.current_turn = None
            return True
        hit = self.main_hit(att, dfn)
        # 受到攻击、伤害结算前（护盾吸收之后）：效果可以减少这次伤害
        if not hit.dodged:
            self.fire("taking_hit", [dfn], {"hit": hit.env(), "_hit": hit})
        # 受到致命伤害时：效果可以免疫这次伤害（多个效果都能免疫时，优先级小的生效）
        if not hit.dodged and hit.damage > 0 and hit.damage >= dfn.hp_now:
            if self.fire("fatal", [dfn], {"hit": hit.env()}).prevented:
                hit.damage = 0
                hit.saved = True
        # 扣血前（免疫致命伤害之后）：效果还可以减少这次伤害
        if not hit.dodged and hit.damage > 0:
            self.fire("before_damage", [dfn], {"hit": hit.env(), "_hit": hit})
        if hit.damage > 0:
            self.fire("dealt_damage", [att], {"hit": hit.env(),
                                              "dealt": {"amount": hit.damage, "attack": True, "by": ZeroDict()}})
        if not hit.dodged:
            # 命中后（没被闪避）、伤害结算前：效果可以提升这次攻击的伤害
            self.fire("on_hit", [att], {"hit": hit.env(), "_hit": hit})
            if hit.crit:
                self.fire("on_crit", [att], {"hit": hit.env(), "_hit": hit})
        turn.damage, turn.crit, turn.dodged, turn.absorbed = hit.damage, hit.crit, hit.dodged, hit.absorbed
        turn.total += hit.damage
        extra = {"hit": hit.env()}
        self.deal(dfn, hit.damage)
        if att.side == PLAYER:
            self._lifesteal(att, hit.damage, hit.dodged, turn)
        self.fire("after_attack", [att], extra)
        if dfn.dead:
            self.fire("kill", [att], extra)
        if hit.dodged:
            self.fire("on_dodge", [dfn], extra)
        self.fire("damage_taken", [dfn], extra)
        self.fire("hp_below", [dfn])
        if att.side == PLAYER:
            if hit.dodged:
                self.monster_dodges += 1
            elif hit.crit:
                self.player_crits += 1
        elif hit.dodged:
            self.player_dodges += 1
        turn.player_hp, turn.monster_hp = self.player.hp_now, self.monster.hp_now
        self.turns.append(turn)
        self.current_turn = None
        if att.side == PLAYER and att.spec.combo_chance and not dfn.dead and not att.dead \
                and self.rng.roll(att.spec.combo_chance):
            self._combo(att, dfn)
        return dfn.dead or att.dead

    def _lifesteal(self, att: Fighter, damage: int, dodged: bool, turn: Turn) -> None:
        """泣血符：这次攻击造成的伤害按比例回血。"""
        pct = att.spec.lifesteal_pct
        if pct and not dodged and damage > 0:
            heal = damage * pct // 100
            if heal > 0:
                att.hp_now = min(att.hp_max, att.hp_now + heal)
                turn.notes.append(f"泣血符：吸血+{heal}")
                self.touch()

    def _combo(self, att: Fighter, dfn: Fighter) -> None:
        """连击符：再普通攻击一次（只结算伤害和泣血符，不触发攻击后的效果）。"""
        turn = Turn(self.round_no, att.side, notes=["连击符：额外攻击"])
        self.current_turn = turn
        hit = self.main_hit(att, dfn)
        self.deal(dfn, hit.damage)
        if not hit.dodged and hit.damage > 0 and att.spec.lifesteal_pct:
            heal = hit.damage * att.spec.lifesteal_pct // 100
            if heal > 0:
                att.hp_now = min(att.hp_max, att.hp_now + heal)
                self.touch()
        turn.damage, turn.crit, turn.dodged, turn.total = hit.damage, hit.crit, hit.dodged, hit.damage
        turn.player_hp, turn.monster_hp = self.player.hp_now, self.monster.hp_now
        self.turns.append(turn)
        self.current_turn = None

    def _flush_round_start(self) -> None:
        """回合开始时效果造成的伤害：击杀了就单独记一行战报，否则并到这一方下次出手的战报里。"""
        for side, fighter in ((PLAYER, self.player), (MONSTER, self.monster)):
            if self.pending[side] and fighter.foe.dead:
                turn = Turn(self.round_no, side, parts=list(self.pending[side]))
                turn.total = sum(v for _, v in turn.parts)
                turn.player_hp, turn.monster_hp = self.player.hp_now, self.monster.hp_now
                self.turns.append(turn)
                self.pending[side] = []

    # ---- 整场

    def run(self) -> BattleResult:
        self.player_crits = self.player_dodges = self.monster_dodges = 0
        both = [self.player, self.monster]
        if self.entry:
            self.fire("battle_start", both)
            self.fire("hp_below", both)
        if self.monster.world_boss:
            player_first = False
        else:
            player_first = bool(self.f("first_strike", agi=self.player.panel.get("agi", 0),
                                       foe_agi=self.monster.panel.get("agi", 0)))
        order = (self.player, self.monster) if player_first else (self.monster, self.player)
        idle_limit = int(self.rules.setting("draw_idle_rounds", 50))
        idle = 0
        timeout = draw = False
        while True:
            if self.max_rounds is not None and self.round_no >= self.max_rounds:
                timeout = True
                break
            self.round_no += 1
            self.touch()
            hp_before = (self.player.hp_now, self.monster.hp_now)
            self.fire("round_start", both)
            self._flush_round_start()
            if self.player.dead or self.monster.dead:
                break
            if self.attack(order[0], order[1]) or self.attack(order[1], order[0]):
                break
            self.fire("round_end", both)
            for fighter in both:
                fighter.tick_round()
            if self.max_rounds is None:
                idle = idle + 1 if (self.player.hp_now, self.monster.hp_now) == hp_before else 0
                if idle >= idle_limit:
                    draw = True
                    break
        self.fire("battle_end", both)
        won = self.monster.dead and not self.player.dead and not timeout and not draw
        carry = {
            "vars": {k: self.player.vars[k] for k in sorted(self.player.carry_keys)},
            "once_run": sorted(self.player.once_run),
        }
        return BattleResult(
            won=won, timeout=timeout, draw=draw, player_first=player_first, rounds=self.round_no,
            player_hp=self.player.hp_now, monster_hp=self.monster.hp_now,
            player_max_hp=self.player.hp_max, monster_max_hp=self.monster.hp_max,
            turns=self.turns, notes=self.notes, carry=carry,
            player_crits=self.player_crits, player_dodges=self.player_dodges,
            monster_dodges=self.monster_dodges, triggered=dict(self.triggered),
            foe_stacks={k: int(v) for k, v in self.monster.stacks.items() if v},
            notes_timeline=self.notes_timeline,
        )


def fight(
    rules: RuleSet,
    player: FighterSpec,
    monster: FighterSpec,
    *,
    seed: int | None = None,
    rng: Rng | None = None,
    hp: int | None = None,
    carry: Mapping[str, Any] | None = None,
    entry: bool = True,
    max_rounds: int | None | str = "default",
) -> BattleResult:
    """打一场。max_rounds 不传用规则里的回合上限；传 None 表示不限回合（连续多回合没有伤害算平局）。

    entry=False 表示爬塔连战的后续战斗：不触发"战斗开始"，沿用 carry 里跨场保留的数据。
    """
    if max_rounds == "default":
        max_rounds = int(rules.setting("max_rounds", 50))
    battle = Battle(rules, player, monster, rng=rng or Rng(seed), hp=hp, carry=carry, entry=entry,
                    max_rounds=max_rounds)  # type: ignore[arg-type]
    return battle.run()
