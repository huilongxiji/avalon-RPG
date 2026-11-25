"""规则库 rules.db 的读写：一套完整的规则（属性、层数、公式、效果、装备、套装、怪物、副本、道具、配方、设定）
存成一个版本；读出一个版本编译成规则快照。

- 写入前先完整编译检查一遍，有问题就不写（RuleError 里列出全部问题）；写入在一个事务里，出错自动回滚。
- 激活一个版本时，原来生效的版本改为"已归档"；每次写入和激活都记一条审计。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone

from avalon_contracts.rules.effect import EffectDef
from avalon_contracts.rules.formula import FormulaDef
from avalon_contracts.rules.item import ItemDef, SetDef, SetTier
from avalon_contracts.rules.monster import DungeonDef, Encounter, MonsterDef, Reward
from avalon_contracts.rules.prop import PropDef, RecipeDef, RecipeInput
from avalon_contracts.rules.setting import SettingDef
from avalon_contracts.rules.stack import StackDef
from avalon_contracts.rules.stat import StatDef

from ..engine.ruleset import RuleSet, build_ruleset
from ..store.models.rules import (
    DungeonRow,
    EffectRow,
    FormulaRow,
    ItemRow,
    ItemSetRow,
    MonsterRow,
    PropRecipeRow,
    PropRow,
    RecipeRow,
    RuleAudit,
    RuleVersion,
    SettingRow,
    StackDefRow,
    StatDefRow,
)
from ..store.tx import transaction

ACTIVE, DRAFT, ARCHIVED = "active", "draft", "archived"


@dataclass
class RuleData:
    """一个版本的全部规则数据（和数据库里的内容一一对应）。"""

    stats: list[StatDef] = field(default_factory=list)
    stacks: list[StackDef] = field(default_factory=list)
    formulas: list[FormulaDef] = field(default_factory=list)
    effects: list[EffectDef] = field(default_factory=list)
    sets: list[SetDef] = field(default_factory=list)
    items: list[ItemDef] = field(default_factory=list)
    monsters: list[MonsterDef] = field(default_factory=list)
    dungeons: list[DungeonDef] = field(default_factory=list)
    props: list[PropDef] = field(default_factory=list)
    recipes: list[RecipeDef] = field(default_factory=list)
    prop_recipes: list[RecipeDef] = field(default_factory=list)
    settings: list[SettingDef] = field(default_factory=list)

    def compile(self, version_id: int | None = None) -> RuleSet:
        return build_ruleset(**{f.name: getattr(self, f.name) for f in fields(self)}, version_id=version_id)

    def counts(self) -> dict[str, int]:
        return {f.name: len(getattr(self, f.name)) for f in fields(self)}


def builtin_data(*, effects: Iterable[EffectDef] = (), sets: Iterable[SetDef] = (), items: Iterable[ItemDef] = (),
                 monsters: Iterable[MonsterDef] = (), dungeons: Iterable[DungeonDef] = (),
                 props: Iterable[PropDef] = (), recipes: Iterable[RecipeDef] = (),
                 prop_recipes: Iterable[RecipeDef] = ()) -> RuleData:
    """内置的属性、层数、公式、全局机制、设定 + 给定的装备等数据（第一个版本用）。"""
    from . import builtin

    return RuleData(
        stats=list(builtin.STATS), stacks=list(builtin.STACKS), formulas=list(builtin.FORMULAS),
        effects=[*builtin.GLOBAL_EFFECTS, *effects], sets=list(sets), items=list(items), monsters=list(monsters),
        dungeons=list(dungeons), props=list(props), recipes=list(recipes), prop_recipes=list(prop_recipes),
        settings=list(builtin.SETTINGS),
    )


# ---------------------------------------------------------------- 写入


def _rows(version_id: int, data: RuleData, only: Iterable[str] | None = None) -> list[tuple[type, list]]:
    """每类数据对应的表和要写入的行（顺序和 RuleData 的字段一致）。only：只要这几类（字段名）。"""
    v = {"version_id": version_id}
    out = [
        (StatDefRow, [StatDefRow(**v, **s.model_dump()) for s in data.stats]),
        (StackDefRow, [StackDefRow(**v, **s.model_dump()) for s in data.stacks]),
        (FormulaRow, [FormulaRow(**v, **f.model_dump()) for f in data.formulas]),
        (EffectRow, [EffectRow(**v, effect_id=e.id, name=e.name,
                               data=e.model_dump(mode="json", by_alias=True, exclude_none=True))
                     for e in data.effects]),
        (ItemSetRow, [ItemSetRow(**v, name=s.name, tiers=[t.model_dump() for t in s.tiers]) for s in data.sets]),
        (ItemRow, [ItemRow(**v, item_id=i.id, **i.model_dump(exclude={"id"})) for i in data.items]),
        (MonsterRow, [MonsterRow(**v, monster_id=m.id, **m.model_dump(mode="json", exclude={"id"}))
                      for m in data.monsters]),
        (DungeonRow, [DungeonRow(**v, dungeon_id=d.id, **d.model_dump(mode="json", exclude={"id"}))
                      for d in data.dungeons]),
        (PropRow, [PropRow(**v, prop_id=p.id, **p.model_dump(exclude={"id"})) for p in data.props]),
        (RecipeRow, [RecipeRow(**v, recipe_id=r.id, **r.model_dump(mode="json", exclude={"id"}))
                     for r in data.recipes]),
        (PropRecipeRow, [PropRecipeRow(**v, recipe_id=r.id, **r.model_dump(mode="json", exclude={"id"}))
                         for r in data.prop_recipes]),
        (SettingRow, [SettingRow(**v, **s.model_dump(mode="json")) for s in data.settings]),
    ]
    if only is None:
        return out
    wanted = set(only)
    return [pair for f, pair in zip(fields(RuleData), out, strict=True) if f.name in wanted]


async def save_version(data: RuleData, *, actor: str, note: str = "", activate: bool = False,
                       parent_id: int | None = None) -> int:
    """把 data 存成一个新版本（先编译检查，有问题抛 RuleError，什么都不写）。返回版本号。"""
    data.compile()
    async with transaction("rules"):
        version = await RuleVersion.create(parent_id=parent_id, status=DRAFT, note=note, created_by=actor)
        for model, rows in _rows(version.id, data):
            if rows:
                await model.bulk_create(rows)
        await RuleAudit.create(version=version, actor=actor, action="create", target=f"版本 {version.id}",
                               after=data.counts())
        if activate:
            await _activate(version, actor)
    return version.id


async def replace_rows(version_id: int, data: RuleData, only: Iterable[str]) -> None:
    """把一个版本里这几类数据整类换成 data 里的（调用方负责先编译检查、开事务）。"""
    for model, rows in _rows(version_id, data, only):
        await model.filter(version_id=version_id).delete()
        if rows:
            await model.bulk_create(rows)


async def activate_version(version_id: int, *, actor: str) -> None:
    """让一个版本生效（先编译检查）。原来生效的版本改为已归档。"""
    data = await load_data(version_id)
    data.compile(version_id)
    async with transaction("rules"):
        version = await RuleVersion.get(id=version_id)
        await _activate(version, actor)


async def _activate(version: RuleVersion, actor: str) -> None:
    previous = await RuleVersion.filter(status=ACTIVE).exclude(id=version.id).values_list("id", flat=True)
    await RuleVersion.filter(id__in=list(previous)).update(status=ARCHIVED)
    version.status = ACTIVE
    version.activated_at = datetime.now(timezone.utc)
    await version.save(update_fields=["status", "activated_at"])
    await RuleAudit.create(version=version, actor=actor, action="activate", target=f"版本 {version.id}",
                           before={"active": list(previous)})


# ---------------------------------------------------------------- 读取


async def load_data(version_id: int) -> RuleData:
    """读出一个版本的全部数据（按编号/代号排序，和写入时的顺序无关）。"""
    vid = {"version_id": version_id}
    stats = [StatDef(key=r.key, name=r.name, default=r.default, min=r.min, max=r.max, merge=r.merge,
                     percent=r.percent, show=r.show)
             for r in await StatDefRow.filter(**vid).order_by("id")]
    stacks = [StackDef(key=r.key, name=r.name, owner=r.owner, max=r.max, max_stat=r.max_stat, carry=r.carry,
                       boss_immune=r.boss_immune)
              for r in await StackDefRow.filter(**vid).order_by("id")]
    formulas = [FormulaDef(name=r.name, title=r.title or "", expr=r.expr, params=r.params, description=r.description)
                for r in await FormulaRow.filter(**vid).order_by("id")]
    effects = [EffectDef.model_validate(r.data) for r in await EffectRow.filter(**vid).order_by("id")]
    sets = [SetDef(name=r.name, tiers=[SetTier.model_validate(t) for t in r.tiers])
            for r in await ItemSetRow.filter(**vid).order_by("id")]
    items = [ItemDef(id=r.item_id, name=r.name, slot=r.slot, price=r.price, stats=r.stats,
                     damage_type=r.damage_type, sets=r.sets, effects=r.effects, sponsor=r.sponsor,
                     retired=r.retired)
             for r in await ItemRow.filter(**vid).order_by("item_id")]
    monsters = [MonsterDef(id=r.monster_id, name=r.name, kind=r.kind, level=r.level, no=r.no, stats=r.stats,
                           coins=r.coins, exp=r.exp, rewards=[Reward.model_validate(x) for x in r.rewards],
                           prop_rewards=[Reward.model_validate(x) for x in r.prop_rewards],
                           info_rewards=r.info_rewards, effects=r.effects)
                for r in await MonsterRow.filter(**vid).order_by("id")]
    dungeons = [DungeonDef(id=r.dungeon_id, name=r.name, stamina=r.stamina, hidden_id=r.hidden_id,
                           hidden_rate=r.hidden_rate, encounters=[Encounter.model_validate(x) for x in r.encounters])
                for r in await DungeonRow.filter(**vid).order_by("dungeon_id")]
    props = [PropDef(id=r.prop_id, name=r.name, category=r.category, effect=r.effect, amount=r.amount,
                     blurb=r.blurb, dungeon=r.dungeon, value=r.value)
             for r in await PropRow.filter(**vid).order_by("prop_id")]

    def recipe(r) -> RecipeDef:
        return RecipeDef(id=r.recipe_id, output=r.output, quantity=r.quantity,
                         inputs=[RecipeInput.model_validate(x) for x in r.inputs])

    recipes = [recipe(r) for r in await RecipeRow.filter(**vid).order_by("recipe_id")]
    prop_recipes = [recipe(r) for r in await PropRecipeRow.filter(**vid).order_by("recipe_id")]
    settings = [SettingDef(key=r.key, value=r.value, description=r.description)
                for r in await SettingRow.filter(**vid).order_by("id")]
    return RuleData(stats=stats, stacks=stacks, formulas=formulas, effects=effects, sets=sets, items=items,
                    monsters=monsters, dungeons=dungeons, props=props, recipes=recipes, prop_recipes=prop_recipes,
                    settings=settings)


async def active_version_id() -> int | None:
    row = await RuleVersion.filter(status=ACTIVE).order_by("-id").first()
    return row.id if row else None


async def load_active() -> RuleSet | None:
    """读出当前生效的版本并编译；还没有生效版本时返回 None。"""
    version_id = await active_version_id()
    if version_id is None:
        return None
    return (await load_data(version_id)).compile(version_id)
