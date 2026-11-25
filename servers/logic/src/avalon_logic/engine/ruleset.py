"""把一个规则版本的数据检查并编译成战斗内核直接使用的对象（设计文档 7.10 节的第 1、2 层校验）。

- 格式：由 avalon_contracts 的 pydantic 模型保证；
- 引用：效果里用到的属性、层数、公式、其他效果都必须存在；
- 表达式：全部编译一遍，写错的地方带中文说明一次性列出来。

编译好的 RuleSet 只读，放进规则快照后由所有战斗共享。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from avalon_contracts.rules.effect import (
    ACTIONS,
    BATTLE_OPS,
    STATIC_OPS,
    TRIGGERS,
    ActionSpec,
    EffectDef,
)
from avalon_contracts.rules.formula import BATTLE_FORMULAS, REQUIRED_FORMULAS, FormulaDef
from avalon_contracts.rules.item import ItemDef, SetDef
from avalon_contracts.rules.monster import DungeonDef, MonsterDef
from avalon_contracts.rules.prop import PropDef, RecipeDef
from avalon_contracts.rules.setting import SettingDef
from avalon_contracts.rules.stack import StackDef
from avalon_contracts.rules.stat import StatDef
from pydantic import ValidationError

from .expr import FORMULAS_KEY, FUNCTIONS, CompiledExpr, ExprError, compile_expr

# 战斗内核目前已经实现的时机和动作；其余的已经定好格式，后续阶段实现（用到时会提示"还没有实现"）
IMPLEMENTED_TRIGGERS = frozenset({
    "battle_start", "round_start", "before_action", "attack", "compute_hit", "segment", "on_hit", "on_crit", "after_attack", "on_dodge", "taking_hit", "fatal", "before_damage", "dealt_damage",
    "damage_taken", "hp_below", "stack_full", "stack_gain", "kill", "round_end", "battle_end",
})
IMPLEMENTED_ACTIONS = frozenset({
    "modify_stat", "damage", "replace_hit", "set_hit", "scale_hit", "reduce_hit", "chase", "execute", "lose_hp", "heal", "shield", "stack", "prevent", "flag", "carry", "note", "random",
})
PANEL_OPS = {"add": "加", "mul": "乘以", "set": "设为"}
DAMAGE_KINDS = {"physical": "物理", "magic": "法术", "true": "真实"}
HIT_PARTS = {"physical": "物理伤害", "magic": "法术伤害", "true": "真实伤害"}
STACK_OPS = {"add": "增加", "remove": "减少", "clear": "清空", "set": "设为"}

# 表达式里能用的变量
FIGHTER_FIELDS = {
    "hp_now": "当前生命", "hp_max": "最大生命", "shield": "当前护盾", "level": "等级",
    "is_player": "是否是玩家", "is_world_boss": "是否是世界BOSS",
}
HIT_FIELDS = {
    "damage": "这次攻击造成的伤害", "crit": "是否暴击", "dodged": "是否被闪避",
    "magic": "是否法术攻击", "physical": "是否物理攻击", "precision": "是否精准攻击",
    "saved": "是否免疫了致命伤害", "multi": "是否多段攻击",
    "true_part": "这次伤害里真实伤害的部分", "precision_crit_dmg": "精准武器这次额外的暴击伤害%",
    "by": "这次普通攻击是哪个效果换成的（hit.by.效果id）",
}
SEG_FIELDS = {"damage": "这一段的伤害", "kind_magic": "这一段是否法术伤害", "chase": "这一段是否追击"}
DEALT_FIELDS = {"amount": "这次造成的伤害", "attack": "是否普通攻击造成的", "by": "由哪个效果造成（dealt.by.效果id）"}
STACK_FIELDS = {"count": "当前层数", "adding": "这次增加的层数", "max": "层数上限"}
WEAPON_FIELDS = {"magic": "法术武器", "physical": "物理武器", "precision": "精准武器", "id": "武器的装备编号"}
EFFECT_NAMES = frozenset({"self", "foe", "round_no", "entry", "hit", "seg", "stack", "dealt", "last", "pieces",
                          "weapon"})
STATIC_NAMES = frozenset({"self", "weapon", "pieces"})


class RuleError(ValueError):
    """规则数据有问题。problems 是全部问题的中文说明。"""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("规则数据有问题：\n" + "\n".join(f"- {p}" for p in problems))


def to_number(value: Any) -> int | float:
    """整数值的小数（如 66.0）统一成整数，保证整除和取整的结果与旧版一致。"""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


# ---------------------------------------------------------------- 编译后的对象


@dataclass(frozen=True)
class Formula:
    name: str
    expr: CompiledExpr
    params: tuple[str, ...]
    description: str = ""
    variables: Mapping[str, str] = field(default_factory=dict)    # 变量名 → 中文说明
    title: str = ""                                               # 中文名称
    # 全部公式（公式里可以调用别的公式）；和 RuleSet.formulas 是同一个字典
    registry: Mapping[str, "Formula"] = field(default_factory=dict, repr=False, compare=False)

    def __call__(self, **values: Any) -> int | float:
        return to_number(self.expr.number({**values, FORMULAS_KEY: self.registry}))


@dataclass(frozen=True)
class Static:
    stat: str
    op: str
    value: CompiledExpr
    cond: CompiledExpr | None
    group: str = ""


@dataclass(frozen=True)
class Aura:
    target: str
    stat: str
    op: str
    value: CompiledExpr
    cond: CompiledExpr | None


@dataclass(frozen=True)
class Action:
    kind: str
    args: Mapping[str, Any]
    exprs: Mapping[str, CompiledExpr]
    cond: CompiledExpr | None
    # random 动作的各个选项：(名称, 动作列表)
    choices: tuple[tuple[str, tuple["Action", ...]], ...] = ()


@dataclass(frozen=True)
class Trigger:
    key: str                       # 效果代号#序号，用来记录"每场一次"、冷却
    on: str
    cond: CompiledExpr | None
    chance: CompiledExpr | None
    once: str | None
    cooldown: int
    priority: int
    stack: str | None
    actions: tuple[Action, ...]


@dataclass(frozen=True)
class Effect:
    id: str
    name: str
    params: Mapping[str, int | float]
    statics: tuple[Static, ...]
    auras: tuple[Aura, ...]
    triggers: tuple[Trigger, ...]
    definition: EffectDef

    @property
    def desc(self) -> str:
        return self.definition.render_desc()


@dataclass(frozen=True)
class RuleSet:
    version_id: int | None
    stats: Mapping[str, StatDef]
    stacks: Mapping[str, StackDef]
    formulas: Mapping[str, Formula]
    effects: Mapping[str, Effect]
    sets: Mapping[str, SetDef] = field(default_factory=dict)
    items: Mapping[int, ItemDef] = field(default_factory=dict)
    monsters: Mapping[str, MonsterDef] = field(default_factory=dict)
    settings: Mapping[str, Any] = field(default_factory=dict)
    # 游戏业务用（战斗内核不读）
    dungeons: Mapping[int, DungeonDef] = field(default_factory=dict)
    props: Mapping[int, PropDef] = field(default_factory=dict)
    recipes: Mapping[int, RecipeDef] = field(default_factory=dict)
    prop_recipes: Mapping[int, RecipeDef] = field(default_factory=dict)

    def formula(self, name: str) -> Formula:
        return self.formulas[name]

    def setting(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    @property
    def global_effects(self) -> tuple[str, ...]:
        return tuple(self.settings.get("global_effects") or ())

    def set_effects(self, set_counts: Mapping[str, int]) -> list[tuple[str, int]]:
        """按每个套装穿了几件，列出生效的效果：[(效果代号, 件数), ...]。"""
        active: list[tuple[str, int]] = []
        for name, count in set_counts.items():
            spec = self.sets.get(name)
            if spec is None:
                continue
            for tier in spec.tiers:
                if count >= tier.pieces:
                    active.extend((effect_id, count) for effect_id in tier.effects)
        return active


# ---------------------------------------------------------------- 编译与校验


class _Builder:
    def __init__(self, stats: Mapping[str, StatDef], stacks: Mapping[str, StackDef],
                 formulas: Mapping[str, tuple[str, ...]] | None = None) -> None:
        self.stats = stats
        self.stacks = stacks
        self.formulas = formulas or {}          # 效果里可以调用的公式：公式名 → 变量名
        self.problems: list[str] = []

    def problem(self, where: str, text: str) -> None:
        self.problems.append(f"{where}：{text}")

    # ---- 表达式

    def expr(self, where: str, source: Any, names: frozenset[str]) -> CompiledExpr | None:
        if isinstance(source, bool) or not isinstance(source, (int, float, str)):
            self.problem(where, "这里要填数字或表达式")
            return None
        text = str(source)
        try:
            compiled = compile_expr(text, names, self.formulas)
        except ExprError as exc:
            self.problem(where, f"表达式「{text}」{exc}")
            return None
        for path in compiled.paths:
            message = self._check_path(path)
            if message:
                self.problem(where, f"表达式「{text}」{message}")
        return compiled

    def _check_path(self, path: tuple[str, ...]) -> str | None:
        root, rest = path[0], path[1:]
        if root in ("self", "foe"):
            if not rest:
                return f"{root} 后面要写属性，例如 {root}.atk"
            head = rest[0]
            if head in ("panel", "base"):
                if len(rest) != 2 or rest[1] not in self.stats:
                    return f"{'.'.join(path)} 里的属性不存在"
                return None
            if head == "stacks":
                if len(rest) != 2 or rest[1] not in self.stacks:
                    return f"层数 {'.'.join(rest[1:]) or '（没写）'} 没有定义"
                return None
            if head == "vars":
                return None if len(rest) == 2 else f"{'.'.join(path)} 的写法应为 {root}.vars.名称"
            if len(rest) != 1:
                return f"{'.'.join(path)} 写法不正确"
            if head in self.stats or head in FIGHTER_FIELDS:
                return None
            return f"属性 {head} 没有定义"
        if root in ("dealt", "hit") and rest and rest[0] == "by":
            if len(rest) != 2:
                return f"{root}.by 的写法应为 {root}.by.效果id"
            return None
        fields_by_root = {"hit": HIT_FIELDS, "dealt": DEALT_FIELDS, "seg": SEG_FIELDS, "stack": STACK_FIELDS, "weapon": WEAPON_FIELDS,
                          "last": {"prevented": "上一个叠层动作是否被取消", "count": "上一个追击动作追击了几段",
                                   "damage": "上一个伤害动作造成的伤害"}}
        if root in fields_by_root:
            if len(rest) != 1 or rest[0] not in fields_by_root[root]:
                allowed = "、".join(f"{root}.{k}" for k in fields_by_root[root])
                return f"{'.'.join(path)} 不存在，可以用：{allowed}"
            return None
        if rest:
            return f"{'.'.join(path)} 写法不正确"
        return None

    # ---- 效果

    def effect(self, definition: EffectDef) -> Effect | None:
        before = len(self.problems)
        where = f"效果 {definition.id}（{definition.name}）"
        params = {k: to_number(v) for k, v in definition.params.items()}
        clash = set(params) & (EFFECT_NAMES | {"round_no"})
        if clash:
            self.problem(where, f"参数名不能用这些保留名称：{'、'.join(sorted(clash))}")
        effect_names = EFFECT_NAMES | frozenset(params)
        static_names = STATIC_NAMES | frozenset(params)

        statics: list[Static] = []
        for i, mod in enumerate(definition.static, 1):
            w = f"{where} 的第 {i} 条静态加成"
            if mod.stat not in self.stats:
                self.problem(w, f"属性 {mod.stat} 没有定义")
            if mod.op not in STATIC_OPS:
                self.problem(w, f"不支持的加成方式 {mod.op}")
            value = self.expr(w, mod.value, static_names)
            cond = self.expr(w + "的条件", mod.if_, static_names) if mod.if_ else None
            if value is not None:
                statics.append(Static(mod.stat, mod.op, value, cond, mod.group or ""))

        auras: list[Aura] = []
        for i, aura in enumerate(definition.auras, 1):
            w = f"{where} 的第 {i} 条持续加成"
            if aura.stat not in self.stats:
                self.problem(w, f"属性 {aura.stat} 没有定义")
            value = self.expr(w, aura.value, effect_names)
            cond = self.expr(w + "的条件", aura.if_, effect_names) if aura.if_ else None
            if value is not None:
                auras.append(Aura(aura.target, aura.stat, aura.op, value, cond))

        triggers: list[Trigger] = []
        for i, spec in enumerate(definition.triggers, 1):
            w = f"{where} 的第 {i} 段触发逻辑（{TRIGGERS.get(spec.on, spec.on)}）"
            if spec.on not in IMPLEMENTED_TRIGGERS:
                self.problem(w, "这个时机还没有实现")
            if spec.stack is not None and spec.stack not in self.stacks:
                self.problem(w, f"层数 {spec.stack} 没有定义")
            cond = self.expr(w + "的条件", spec.if_, effect_names) if spec.if_ else None
            chance = self.expr(w + "的概率", spec.chance, effect_names) if spec.chance is not None else None
            actions = self.actions(w, spec.do, effect_names)
            triggers.append(Trigger(
                key=f"{definition.id}#{i}", on=spec.on, cond=cond, chance=chance, once=spec.once,
                cooldown=spec.cooldown, priority=spec.priority, stack=spec.stack, actions=actions,
            ))
        if len(self.problems) > before:
            return None
        return Effect(definition.id, definition.name, params, tuple(statics), tuple(auras),
                      tuple(triggers), definition)

    def actions(self, where: str, specs: Iterable[ActionSpec | Mapping[str, Any]],
                names: frozenset[str]) -> tuple[Action, ...]:
        built: list[Action] = []
        if not isinstance(specs, (list, tuple)):
            self.problem(where, "do 必须是动作列表")
            return ()
        for i, raw in enumerate(specs, 1):
            try:
                spec = raw if isinstance(raw, ActionSpec) else ActionSpec.model_validate(raw)
            except ValidationError:
                self.problem(where, f"第 {i} 个动作格式不正确")
                continue
            w = f"{where} 的第 {i} 个动作（{ACTIONS.get(spec.action, spec.action)}）"
            action = self.action(w, spec, names)
            if action is not None:
                built.append(action)
        return tuple(built)

    def action(self, where: str, spec: ActionSpec, names: frozenset[str]) -> Action | None:
        kind = spec.action
        args = spec.args()
        if kind not in IMPLEMENTED_ACTIONS:
            self.problem(where, "这个动作还没有实现")
            return None
        cond = self.expr(where + "的条件", spec.if_, names) if spec.if_ else None
        exprs: dict[str, CompiledExpr] = {}
        choices: list[tuple[str, tuple[Action, ...]]] = []

        def need_expr(key: str, default: Any = None) -> None:
            source = args.get(key, default)
            if source is None:
                self.problem(where, f"缺少 {key}")
                return
            compiled = self.expr(where, source, names)
            if compiled is not None:
                exprs[key] = compiled

        def need_choice(key: str, options: Mapping[str, str], default: str | None = None) -> None:
            value = args.get(key, default)
            if not isinstance(value, str) or value not in options:
                allowed = "、".join(f"{k}（{v}）" for k, v in options.items())
                self.problem(where, f"{key} 只能填：{allowed}")

        target_ok = {"self": "自己", "foe": "对手"}
        if kind == "modify_stat":
            if not isinstance(args.get("stat"), str) or args.get("stat") not in self.stats:
                self.problem(where, f"属性 {args.get('stat')} 没有定义")
            need_choice("target", target_ok, "self")
            scope = args.get("scope", "battle")
            need_choice("scope", {"battle": "战斗中的加成", "panel": "直接改面板"}, "battle")
            need_choice("op", PANEL_OPS if scope == "panel" else BATTLE_OPS, "add" if scope != "panel" else None)
            need_expr("value")
            if args.get("rounds") is not None:
                need_expr("rounds")
        elif kind == "damage":
            need_choice("kind", DAMAGE_KINDS)
            need_choice("target", target_ok, "foe")
            need_expr("value")
            for key in ("ignore_def", "ignore_resist", "crit_rate", "crit_dmg"):
                if args.get(key) is not None:
                    need_expr(key)
            skip = args.get("not_lowered_by")
            if skip is not None and (not isinstance(skip, list) or not all(isinstance(x, str) for x in skip)):
                self.problem(where, "not_lowered_by 要写成效果 id 的列表")
        elif kind == "set_hit":
            need_choice("part", HIT_PARTS)
            need_expr("value")
        elif kind in ("scale_hit", "reduce_hit"):
            need_expr("value")
            if args.get("base") is not None:
                need_expr("base")
        elif kind == "chase":
            for key in ("base", "pct", "decay", "crit_rate", "crit_dmg"):
                need_expr(key)
            if not isinstance(args.get("counter"), str) or not args.get("counter"):
                self.problem(where, "counter 要写一个标记名（记本回合已追击的次数）")
        elif kind == "execute":
            need_choice("target", target_ok, "foe")
        elif kind == "lose_hp":
            need_expr("value")
        elif kind == "replace_hit":
            hits = args.get("hits")
            if not isinstance(hits, list) or not hits or not all(isinstance(h, Mapping) for h in hits):
                self.problem(where, "hits 要写成一段或多段攻击的列表，每段写 kind 和 value")
            else:
                if args.get("multi") is False and len(hits) != 1:
                    self.problem(where, "multi 写成 false（单段）时 hits 只能写一段")
                for i, hit in enumerate(hits):
                    if not isinstance(hit.get("kind"), str) or hit.get("kind") not in DAMAGE_KINDS:
                        allowed = "、".join(f"{k}（{v}）" for k, v in DAMAGE_KINDS.items())
                        self.problem(where, f"第 {i + 1} 段的 kind 只能填：{allowed}")
                    if hit.get("value") is None:
                        self.problem(where, f"第 {i + 1} 段缺少 value")
                        continue
                    compiled = self.expr(where, hit["value"], names)
                    if compiled is not None:
                        exprs[f"hits.{i}"] = compiled
        elif kind in ("heal", "shield"):
            need_choice("target", target_ok, "self")
            need_expr("value")
        elif kind == "stack":
            name = args.get("name")
            if not isinstance(name, str) or name not in self.stacks:
                self.problem(where, f"层数 {name} 没有定义")
            need_choice("op", STACK_OPS, "add")
            if args.get("target") is not None:
                need_choice("target", target_ok)
            if args.get("op", "add") != "clear":
                need_expr("value", 1)
        elif kind in ("flag", "carry"):
            if not isinstance(args.get("name"), str) or not args.get("name"):
                self.problem(where, "缺少标记名称 name")
            need_expr("value", 1)
        elif kind == "note":
            if not isinstance(args.get("text"), str):
                self.problem(where, "缺少说明文字 text")
        elif kind == "random":
            options = args.get("choices")
            if not isinstance(options, list) or not options:
                self.problem(where, "choices 里至少要有一个选项")
            else:
                for j, option in enumerate(options, 1):
                    if not isinstance(option, Mapping) or not option.get("do"):
                        self.problem(where, f"第 {j} 个选项缺少 do")
                        continue
                    label = str(option.get("label") or f"选项{j}")
                    sub = self.actions(f"{where} 的选项「{label}」", option["do"], names)
                    choices.append((label, sub))
                # 权重：整数或表达式（比如参数名）；写了就每个选项都要写
                weights = [o.get("weight") for o in options if isinstance(o, Mapping)]
                if any(w is not None for w in weights):
                    if any(w is None or isinstance(w, bool) for w in weights):
                        self.problem(where, "写了权重（weight）就每个选项都要写")
                    else:
                        for j, w in enumerate(weights):
                            compiled = self.expr(f"{where} 第 {j + 1} 个选项的权重", w, names)
                            if compiled is not None:
                                exprs[f"weight.{j}"] = compiled
                        args["_weighted"] = len(weights)
        return Action(kind, dict(args), exprs, cond, tuple(choices))


def build_ruleset(
    *,
    stats: Iterable[StatDef],
    stacks: Iterable[StackDef],
    formulas: Iterable[FormulaDef],
    effects: Iterable[EffectDef],
    sets: Iterable[SetDef] = (),
    items: Iterable[ItemDef] = (),
    monsters: Iterable[MonsterDef] = (),
    settings: Iterable[SettingDef] = (),
    dungeons: Iterable[DungeonDef] = (),
    props: Iterable[PropDef] = (),
    recipes: Iterable[RecipeDef] = (),
    prop_recipes: Iterable[RecipeDef] = (),
    version_id: int | None = None,
) -> RuleSet:
    """检查并编译一个规则版本。有问题时抛出 RuleError，里面列出全部问题。"""
    problems: list[str] = []
    stat_map = {s.key: s for s in stats}
    stack_map = {s.key: s for s in stacks}
    setting_map = {s.key: s.value for s in settings}
    from ..rules.game_defaults import validate_settings
    problems.extend(validate_settings(setting_map))
    formulas = list(formulas)
    signatures = {f.name: tuple(f.params) for f in formulas}
    builder = _Builder(stat_map, stack_map, signatures)

    for stack in stack_map.values():
        if stack.max_stat is not None and stack.max_stat not in stat_map:
            problems.append(f"层数 {stack.name} 的上限属性 {stack.max_stat} 不存在")

    formula_map: dict[str, Formula] = {}
    for definition in formulas:
        where = f"公式「{definition.title or BATTLE_FORMULAS.get(definition.name) or definition.name}」"
        if definition.name in formula_map:
            problems.append(f"{where}：公式代号 {definition.name} 重复")
            continue
        if definition.name in FUNCTIONS:
            problems.append(f"{where}：代号 {definition.name} 和自带函数重名")
            continue
        try:
            compiled = compile_expr(definition.expr, frozenset(definition.params), signatures)
        except ExprError as exc:
            problems.append(f"{where}：{exc}（能用的变量：{'、'.join(definition.params) or '无'}）")
            continue
        formula_map[definition.name] = Formula(
            definition.name, compiled, tuple(definition.params), definition.description, dict(definition.params),
            definition.title or BATTLE_FORMULAS.get(definition.name, ""), formula_map)
    for name in REQUIRED_FORMULAS:
        if name not in formula_map:
            problems.append(f"缺少公式「{BATTLE_FORMULAS.get(name, name)}」（{name}），游戏计算要用到它")
    problems.extend(_formula_cycles(formula_map))
    if not problems:
        from ..rules.game_defaults import validate_formulas

        problems.extend(validate_formulas(formula_map, setting_map))

    effect_map: dict[str, Effect] = {}
    for definition in effects:
        if definition.id in effect_map:
            problems.append(f"效果代号 {definition.id} 重复")
            continue
        compiled_effect = builder.effect(definition)
        if compiled_effect is not None:
            effect_map[definition.id] = compiled_effect

    for key in (setting_map.get("global_effects") or ()):
        if key not in effect_map:
            problems.append(f"设定 global_effects 里的效果 {key} 不存在")
    for pct_key, target in (setting_map.get("percent_stats") or {}).items():
        if pct_key not in stat_map or target not in stat_map:
            problems.append(f"设定 percent_stats 里的 {pct_key} → {target} 引用了不存在的属性")

    set_map: dict[str, SetDef] = {}
    for spec in sets:
        set_map[spec.name] = spec
        for tier in spec.tiers:
            for effect_id in tier.effects:
                if effect_id not in effect_map:
                    problems.append(f"套装 {spec.name} 的 {tier.pieces} 件效果 {effect_id} 不存在")

    item_map: dict[int, ItemDef] = {}
    for item in items:
        where = f"装备 {item.name}（编号 {item.id}）"
        if item.id in item_map:
            problems.append(f"{where}：编号重复")
        item_map[item.id] = item
        for key in item.stats:
            if key not in stat_map:
                problems.append(f"{where}：属性 {key} 没有定义")
        for name in item.sets:
            if name not in set_map:
                problems.append(f"{where}：套装 {name} 不存在")
        for effect_id in item.effects:
            if effect_id not in effect_map:
                problems.append(f"{where}：效果 {effect_id} 不存在")

    monster_map = {m.id: m for m in monsters}
    for monster in monster_map.values():
        for key in monster.stats:
            if key not in stat_map:
                problems.append(f"怪物 {monster.name}：属性 {key} 没有定义")
        for effect_id in monster.effects:
            if effect_id not in effect_map:
                problems.append(f"怪物 {monster.name}：效果 {effect_id} 不存在")

    dungeon_map, prop_map, recipe_map, prop_recipe_map = _check_game_data(
        problems, monster_map, item_map, dungeons, props, recipes, prop_recipes)

    problems = builder.problems + problems
    if problems:
        raise RuleError(problems)
    return RuleSet(
        version_id=version_id,
        stats=stat_map,
        stacks=stack_map,
        formulas=formula_map,
        effects=effect_map,
        sets=set_map,
        items=item_map,
        monsters=monster_map,
        settings=setting_map,
        dungeons=dungeon_map,
        props=prop_map,
        recipes=recipe_map,
        prop_recipes=prop_recipe_map,
    )


def _formula_cycles(formulas: Mapping[str, Formula]) -> list[str]:
    """公式之间不能循环调用（A 调用 B、B 又调用 A），否则会算不完。"""
    out: list[str] = []
    state: dict[str, int] = {}      # 1 正在检查，2 检查完

    def visit(name: str, chain: list[str]) -> None:
        if state.get(name) == 2 or name not in formulas:
            return
        if state.get(name) == 1:
            loop = chain[chain.index(name):] + [name]
            out.append("公式循环调用：" + " → ".join(formulas[n].title or n for n in loop))
            return
        state[name] = 1
        for callee in sorted(formulas[name].expr.calls):
            visit(callee, chain + [name])
        state[name] = 2

    for name in formulas:
        visit(name, [])
    return out


def _check_game_data(problems: list[str], monsters: Mapping[str, MonsterDef], items: Mapping[int, ItemDef],
                     dungeons: Iterable[DungeonDef], props: Iterable[PropDef], recipes: Iterable[RecipeDef],
                     prop_recipes: Iterable[RecipeDef]):
    """副本、道具、配方、掉落：编号不重复，引用的怪物、装备、道具都存在。"""
    prop_map: dict[int, PropDef] = {}
    for prop in props:
        if prop.id in prop_map:
            problems.append(f"道具 {prop.name}（编号 {prop.id}）：编号重复")
        prop_map[prop.id] = prop
    names = {i.name for i in items.values()} | {p.name for p in prop_map.values()}
    for monster in monsters.values():
        for reward in [*monster.rewards, *monster.prop_rewards]:
            if reward.name not in names:
                problems.append(f"怪物 {monster.name}：掉落 {reward.name} 不是已有的装备或道具")
    dungeon_map: dict[int, DungeonDef] = {}
    for dungeon in dungeons:
        where = f"副本 {dungeon.name}（编号 {dungeon.id}）"
        if dungeon.id in dungeon_map:
            problems.append(f"{where}：编号重复")
        dungeon_map[dungeon.id] = dungeon
        for encounter in dungeon.encounters:
            if encounter.monster_id not in monsters:
                problems.append(f"{where}：怪物 {encounter.monster_id} 不存在")
        if dungeon.hidden_id and dungeon.hidden_id not in monsters:
            problems.append(f"{where}：隐秘怪物 {dungeon.hidden_id} 不存在")
    recipe_maps: list[dict[int, RecipeDef]] = []
    for label, group in (("合成配方", recipes), ("道具合成配方", prop_recipes)):
        out: dict[int, RecipeDef] = {}
        for recipe in group:
            where = f"{label} {recipe.output}（编号 {recipe.id}）"
            if recipe.id in out:
                problems.append(f"{where}：编号重复")
            out[recipe.id] = recipe
            for name in [recipe.output, *(x.name for x in recipe.inputs)]:
                if name not in names:
                    problems.append(f"{where}：{name} 不是已有的装备或道具")
        recipe_maps.append(out)
    return dungeon_map, prop_map, recipe_maps[0], recipe_maps[1]


def default_ruleset(*, effects: Iterable[EffectDef] = (), sets: Iterable[SetDef] = (),
                    items: Iterable[ItemDef] = (), monsters: Iterable[MonsterDef] = ()) -> RuleSet:
    """内置默认规则 + 额外的效果/套装/装备/怪物，测试和第一个规则版本用。"""
    from ..rules import builtin

    return build_ruleset(
        stats=builtin.STATS,
        stacks=builtin.STACKS,
        formulas=builtin.FORMULAS,
        effects=[*builtin.GLOBAL_EFFECTS, *effects],
        sets=sets,
        items=items,
        monsters=monsters,
        settings=builtin.SETTINGS,
    )
