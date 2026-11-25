"""从规则数据生成网站"装备管理"页面要显示的内容（卡片列表、装备详情）。

只读、只做整理：不改规则，不跑战斗。API 后端把结果原样转给网站。
"""

from __future__ import annotations

import re

from avalon_contracts.api.rules_admin import (
    EffectBrief,
    EffectDetail,
    ExprDetail,
    FormulaRef,
    ItemCard,
    ItemDetail,
    ItemGroup,
    ItemListResponse,
    SetDetail,
    SetRef,
    SetSummary,
    StatValue,
    TierBrief,
    TierDetail,
)
from avalon_contracts.rules.effect import ACTIONS, TRIGGERS, ActionSpec, EffectDef
from avalon_contracts.rules.formula import BATTLE_FORMULAS, REQUIRED_FORMULAS
from avalon_contracts.rules.item import DAMAGE_LABELS, SLOT_LABELS, ItemDef

from ..engine.ruleset import RuleSet, to_number
from .explain import Explainer
from .flows import to_models

MAIN_STATS = ("hp", "atk", "defense", "agi", "mp")

# 不同武器类型 / 部位参与的战斗公式
_ATTACK_FORMULAS = {
    "physical": ("def_after_pen", "physical_mitigation", "level_coef_taken", "physical_damage", "crit_hit", "amplify"),
    "magic": ("resist_after_pen", "level_coef_taken", "level_reduce", "amplify"),
    "precision": ("precision_crit", "precision_crit_dmg", "precision_pen_pct", "precision_flat_pen",
                  "def_after_pen", "physical_mitigation", "level_coef_taken", "physical_damage", "crit_hit", "amplify"),
}
_DEFENSE_FORMULAS = ("physical_mitigation", "physical_damage", "level_coef_dealt", "scale_dealt", "shield_overflow")
_DAMAGE_KIND_FORMULAS = {"physical": ("def_after_pen", "physical_mitigation", "physical_damage"),
                         "magic": ("resist_after_pen", "level_reduce"), "true": ("level_reduce",)}


# 动作里可以写表达式的参数 → 中文名
_ACTION_EXPRS = (("value", "数值"), ("rounds", "回合数"), ("base", "基数"), ("pct", "比例"), ("decay", "每次降低"),
                 ("crit_rate", "暴击率"), ("crit_dmg", "暴击伤害"), ("ignore_def", "无视防御"),
                 ("ignore_resist", "无视法抗"))


def _stat_value(rules: RuleSet, key: str, value: float) -> StatValue:
    spec = rules.stats.get(key)
    return StatValue(key=key, name=spec.name if spec else key, value=to_number(value),
                     percent=bool(spec and spec.percent))


def _effects_of(rules: RuleSet, item: ItemDef) -> list[str]:
    ids = list(item.effects)
    for name in item.sets:
        spec = rules.sets.get(name)
        if spec:
            for tier in spec.tiers:
                ids.extend(tier.effects)
    return ids


def item_card(rules: RuleSet, item: ItemDef, *, changed: bool = False, added: bool = False,
              problems: int = 0) -> ItemCard:
    stats = {k: v for k, v in item.stats.items() if v}
    main = [_stat_value(rules, k, stats[k]) for k in MAIN_STATS if k in stats]
    extra = [_stat_value(rules, k, v) for k, v in stats.items() if k not in MAIN_STATS]
    briefs = [rules.effects[e].desc for e in _effects_of(rules, item) if e in rules.effects]
    brief = "；".join(briefs)
    if len(brief) > 60:
        brief = brief[:59] + "…"
    weapon = item.slot == "weapon"
    damage = item.damage_type or ("physical" if weapon else None)
    return ItemCard(
        id=item.id, name=item.name, slot=item.slot, slot_label=SLOT_LABELS.get(item.slot, item.slot),
        damage_type=damage if weapon else None, damage_label=DAMAGE_LABELS.get(damage) if weapon and damage else None,
        price=item.price, main_stats=main, extra_stats=extra,
        sets=[SetRef(name=n, role="main" if i == 0 else "secondary") for i, n in enumerate(item.sets)],
        effect_brief=brief, changed=changed, added=added, retired=item.retired, problems=problems,
    )


def _set_summary(rules: RuleSet, name: str, count: int) -> SetSummary:
    spec = rules.sets[name]
    tiers = [TierBrief(pieces=t.pieces, effects=[
        EffectBrief(id=e, name=rules.effects[e].name, desc=rules.effects[e].desc)
        for e in t.effects if e in rules.effects]) for t in spec.tiers]
    return SetSummary(name=name, tiers=tiers, item_count=count)


def item_groups(rules: RuleSet, *, changed: set[int] | None = None, added: set[int] | None = None,
                problems: dict[int, int] | None = None) -> ItemListResponse:
    """按主套装分组；副套装只在卡片上显示标签，不重复出现在两个分组里。没有套装的放在最后一组。"""
    changed = changed or set()
    added = added or set()
    problems = problems or {}
    by_set: dict[str, list[ItemCard]] = {name: [] for name in rules.sets}
    loose: list[ItemCard] = []
    for item in sorted(rules.items.values(), key=lambda i: i.id):
        card = item_card(rules, item, changed=item.id in changed, added=item.id in added,
                         problems=problems.get(item.id, 0))
        main = item.sets[0] if item.sets else None
        (by_set[main] if main in by_set else loose).append(card)
    groups = [ItemGroup(set=_set_summary(rules, name, len(cards)), items=cards) for name, cards in by_set.items()]
    if loose:
        groups.append(ItemGroup(set=None, items=loose))
    return ItemListResponse(version_id=rules.version_id, groups=groups, total=len(rules.items))


def effect_detail(rules: RuleSet, definition: EffectDef) -> EffectDetail:
    explainer = Explainer(rules, params=definition.params)
    expressions: list[ExprDetail] = []

    def add(where: str, source: object) -> None:
        # 只是引用一个参数（例如 "reduce"）的不算公式，数值已经写在描述里
        if isinstance(source, str) and source.strip() not in definition.params:
            expressions.append(ExprDetail(where=where, source=source, readable=explainer.expr(source)))

    for i, mod in enumerate(definition.static, 1):
        add(f"静态加成 {i} · 数值", mod.value)
        add(f"静态加成 {i} · 条件", mod.if_)
    for i, aura in enumerate(definition.auras, 1):
        add(f"持续加成 {i} · 数值", aura.value)
        add(f"持续加成 {i} · 条件", aura.if_)
    def add_actions(prefix: str, actions) -> None:
        for j, action in enumerate(actions, 1):
            spec = action if isinstance(action, ActionSpec) else ActionSpec.model_validate(action)
            args = spec.args()
            name = re.sub(r"（.*?）", "", ACTIONS.get(spec.action, spec.action))
            where = f"{prefix} · 第 {j} 个动作（{name}）"
            for key, label in _ACTION_EXPRS:
                add(f"{where}的{label}", args.get(key))
            for k, hit in enumerate(args.get("hits") or [], 1):
                add(f"{where}第 {k} 段的数值", hit.get("value") if isinstance(hit, dict) else None)
            for choice in args.get("choices") or []:
                if isinstance(choice, dict):
                    add(f"{where}「{choice.get('label', '')}」的权重", choice.get("weight"))
                    add_actions(f"{where}「{choice.get('label', '')}」", choice.get("do") or [])
            add(f"{where}的条件", spec.if_)

    for trigger in definition.triggers:
        on = re.sub(r"（.*?）", "", TRIGGERS.get(trigger.on, trigger.on))
        add(f"{on} · 条件", trigger.if_)
        add(f"{on} · 概率", trigger.chance)
        add_actions(on, trigger.do)
    return EffectDetail(
        id=definition.id, name=definition.name, desc=definition.render_desc(), template=definition.desc,
        params=definition.params, logic=explainer.effect_lines(definition), expressions=expressions,
        definition=definition,
    )


def formula_ref(rules: RuleSet, name: str) -> FormulaRef | None:
    formula = rules.formulas.get(name)
    if formula is None:
        return None
    variables = dict(formula.variables)
    readable = Explainer(rules, labels=variables).expr(formula.expr.source)
    used_by = [other.name for other in rules.formulas.values() if name in other.expr.calls]
    return FormulaRef(name=name, title=formula.title or BATTLE_FORMULAS.get(name, ""), description=formula.description,
                      expr=formula.expr.source, readable=readable, variables=dict(variables),
                      required=name in REQUIRED_FORMULAS, calls=sorted(formula.expr.calls), used_by=used_by)


def item_detail(rules: RuleSet, item_id: int) -> ItemDetail:
    item = rules.items[item_id]
    stats = [_stat_value(rules, key, item.stats.get(key, 0)) for key in rules.stats]
    sets: list[SetDetail] = []
    effect_kinds: set[str] = set()
    for i, name in enumerate(item.sets):
        spec = rules.sets.get(name)
        if spec is None:
            continue
        tiers = []
        for tier in spec.tiers:
            details = [effect_detail(rules, rules.effects[e].definition) for e in tier.effects if e in rules.effects]
            tiers.append(TierDetail(pieces=tier.pieces, effects=details))
            for detail in details:
                for trigger in detail.definition.triggers:
                    effect_kinds.update(a.args().get("kind") for a in trigger.do if a.action == "damage")
        members = [other.name for other in rules.items.values() if name in other.sets and other.id != item.id]
        sets.append(SetDetail(name=name, role="main" if i == 0 else "secondary", tiers=tiers, members=members))
    own = [effect_detail(rules, rules.effects[e].definition) for e in item.effects if e in rules.effects]

    if item.slot == "weapon":
        names = list(_ATTACK_FORMULAS[item.damage_type or "physical"])
    else:
        names = list(_DEFENSE_FORMULAS)
    for kind in sorted(k for k in effect_kinds if k):
        names += [n for n in _DAMAGE_KIND_FORMULAS.get(kind, ()) if n not in names]
    formulas = [ref for ref in (formula_ref(rules, n) for n in names) if ref is not None]
    flows = to_models(rules, item, {k for k in effect_kinds if k}, formula_ref)
    notes = ["强化、淬炼后的属性公式在游戏业务迁移阶段（M4）加入，届时这里会显示 +0 到 +15 的属性预览"]
    return ItemDetail(item=item, slot_label=SLOT_LABELS.get(item.slot, item.slot), stats=stats, sets=sets,
                      own_effects=own, formulas=formulas, flows=flows, notes=notes)


def formula_list(rules: RuleSet) -> list[FormulaRef]:
    """全部公式（公式页面用）：名称、说明、原式、中文读法、变量说明。"""
    return [ref for ref in (formula_ref(rules, n) for n in rules.formulas) if ref is not None]
