"""网站修改规则：草稿 → 校验 → 激活（设计文档 7.10 节）。

- 同一时间只有一个草稿，从当前生效版本整份复制。所有修改都写进草稿，玩家那边继续用生效版本。
- 每次保存都把整个草稿重新编译一遍，有问题就不保存，把全部问题用中文返回（数据库不会变）。
- 校验 = 编译 + 自检战斗（每个套装每一档、每件带效果的装备各打几场），全部通过才能激活。
- 激活后马上热更新；以前的版本都留着，可以回滚（重新激活旧版本）。
- 已经在生效版本里的装备只能下架，不能删除（玩家可能已经拥有）；草稿里新建的可以删除。
- 战斗要用的内置公式不能删除，不能改代号和变量名，只能改算法、中文名称和说明。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import fields, replace
from typing import Any

from avalon_contracts.errors import GameError
from avalon_contracts.rules.formula import REQUIRED_FORMULAS, FormulaDef
from avalon_contracts.rules.item import ItemDef
from avalon_contracts.rules.monster import MonsterDef
from avalon_contracts.rules.setting import SettingDef
from avalon_contracts.rules.version import DiffEntry, RuleVersionInfo, ValidateResult

from ..engine.battle import build_monster, build_player, fight
from ..engine.ruleset import RuleError, RuleSet
from ..store.models.rules import RuleAudit, RuleVersion
from ..store.tx import transaction
from . import current
from .locking import serialized
from .store import (
    ACTIVE,
    ARCHIVED,
    DRAFT,
    RuleData,
    activate_version,
    active_version_id,
    load_data,
    replace_rows,
    save_version,
)

log = logging.getLogger("avalon_logic.rules")

DISCARDED = "discarded"

CATEGORY_LABELS = {
    "stats": "属性", "stacks": "层数", "formulas": "公式", "effects": "效果", "sets": "套装", "items": "装备",
    "monsters": "怪物", "dungeons": "副本", "props": "道具", "recipes": "合成配方", "prop_recipes": "道具配方",
    "settings": "设定",
}
_KEY_FIELD = {"stats": "key", "stacks": "key", "formulas": "name", "sets": "name", "settings": "key"}
FIELD_LABELS = {
    "name": "名称", "title": "中文名称", "slot": "部位", "price": "价格", "stats": "属性", "damage_type": "伤害类型",
    "sets": "套装", "effects": "效果", "sponsor": "赞助宝石", "retired": "下架", "expr": "原式", "params": "变量",
    "description": "说明", "tiers": "档位", "value": "数值",
}

# 版本号 → 数据（已归档、生效的版本内容不会再变，可以一直缓存）
_frozen: dict[int, RuleData] = {}
# 草稿：(版本号, 数据, 编译好的规则)
_draft: tuple[int, RuleData, RuleSet] | None = None


def forget_cache() -> None:
    """换了数据库（测试里每次新建内存库）时清掉按版本号缓存的数据，免得拿到别的库里同号版本的内容。"""
    global _draft
    _frozen.clear()
    _draft = None


def info(row: RuleVersion) -> RuleVersionInfo:
    return RuleVersionInfo(id=row.id, parent_id=row.parent_id,  # type: ignore[attr-defined]
                           status=row.status, note=row.note, created_by=row.created_by,  # type: ignore[arg-type]
                           created_at=row.created_at, activated_at=row.activated_at)


async def draft_row() -> RuleVersion | None:
    return await RuleVersion.filter(status=DRAFT).order_by("-id").first()


async def frozen_data(version_id: int) -> RuleData:
    if version_id not in _frozen:
        _frozen[version_id] = await load_data(version_id)
    return _frozen[version_id]


async def draft() -> tuple[RuleVersion, RuleData, RuleSet]:
    """当前草稿（没有草稿时报错）。"""
    global _draft
    row = await draft_row()
    if row is None:
        raise GameError("rules_not_draft", "现在没有草稿，请先点「新建草稿」")
    if _draft is None or _draft[0] != row.id:
        data = await load_data(row.id)
        _draft = (row.id, data, _compile(data, row.id))
    return row, _draft[1], _draft[2]


async def parent_of(row: RuleVersion) -> RuleData | None:
    parent_id = row.parent_id  # type: ignore[attr-defined]
    return await frozen_data(parent_id) if parent_id else None


def _compile(data: RuleData, version_id: int | None) -> RuleSet:
    try:
        return data.compile(version_id)
    except RuleError as exc:
        raise GameError("rules_invalid", "改动没有保存：" + exc.problems[0], problems=exc.problems) from exc


def _dump(obj: Any) -> Any:
    return obj.model_dump(mode="json", by_alias=True, exclude_none=True) if obj is not None else None


# ---------------------------------------------------------------- 草稿


@serialized
async def create_draft(*, actor: str, note: str = "") -> RuleVersionInfo:
    existing = await draft_row()
    if existing is not None:
        raise GameError("rules_conflict", f"已经有一个草稿（版本 {existing.id}），请先激活或放弃它")
    active = await active_version_id()
    if active is None:
        raise GameError("not_found", "规则库尚未初始化，请先导入并激活首个规则版本，再创建草稿")
    data = await frozen_data(active)
    version_id = await save_version(data, actor=actor, note=note or "网站修改", parent_id=active)
    row = await RuleVersion.get(id=version_id)
    await RuleAudit.create(version=row, actor=actor, action="create_draft", target=f"版本 {version_id}",
                           before={"parent": active})
    return info(row)


@serialized
async def discard_draft(*, actor: str) -> None:
    """放弃草稿：版本记录和审计留着（状态改为已放弃），数据删掉。"""
    global _draft
    row, _, _ = await draft()
    async with transaction("rules"):
        await replace_rows(row.id, RuleData(), [f.name for f in fields(RuleData)])
        row.status = DISCARDED
        await row.save(update_fields=["status"])
        await RuleAudit.create(version=row, actor=actor, action="discard", target=f"版本 {row.id}")
    _draft = None


async def _commit(row: RuleVersion, data: RuleData, only: list[str], *, actor: str, action: str, target: str,
                  before: Any = None, after: Any = None) -> RuleSet:
    """编译检查通过后才写入；写入和审计在一个事务里。"""
    global _draft
    rules = _compile(data, row.id)
    async with transaction("rules"):
        current_row = await RuleVersion.get(id=row.id)
        if current_row.status != DRAFT:
            raise GameError("rules_not_draft")
        await replace_rows(row.id, data, only)
        await RuleAudit.create(version=row, actor=actor, action=action, target=target, before=before, after=after)
    _draft = (row.id, data, rules)
    return rules


# ---------------------------------------------------------------- 装备


@serialized
async def save_item(item_id: int | None, item: ItemDef, *, actor: str) -> ItemDef:
    """item_id 为 None 时新建（编号自动取最大编号 + 1），否则修改这件装备（编号不能改）。"""
    row, data, _ = await draft()
    parent = await parent_of(row)
    items = list(data.items)
    if item_id is None:
        used = [i.id for i in items] + ([i.id for i in parent.items] if parent else [])
        item = item.model_copy(update={"id": max(used, default=0) + 1})
        items.append(item)
        before, action = None, "create_item"
    else:
        index = next((n for n, i in enumerate(items) if i.id == item_id), None)
        if index is None:
            raise GameError("not_found", f"没有编号为 {item_id} 的装备")
        before, action = _dump(items[index]), "edit_item"
        item = item.model_copy(update={"id": item_id})
        items[index] = item
    item = item.model_copy(update={"stats": {k: v for k, v in item.stats.items() if v}})
    items = [item if i.id == item.id else i for i in items]
    await _commit(row, replace(data, items=items), ["items"], actor=actor, action=action,
                  target=f"装备 {item.id} {item.name}", before=before, after=_dump(item))
    return item


@serialized
async def delete_item(item_id: int, *, actor: str) -> None:
    row, data, _ = await draft()
    parent = await parent_of(row)
    item = next((i for i in data.items if i.id == item_id), None)
    if item is None:
        raise GameError("not_found", f"没有编号为 {item_id} 的装备")
    if parent and any(i.id == item_id for i in parent.items):
        raise GameError("invalid", f"「{item.name}」在生效版本里已经有了，玩家可能已经拥有，只能下架，不能删除")
    await _commit(row, replace(data, items=[i for i in data.items if i.id != item_id]), ["items"], actor=actor,
                  action="delete_item", target=f"装备 {item_id} {item.name}", before=_dump(item))


# ---------------------------------------------------------------- 公式


@serialized
async def save_formula(name: str | None, formula: FormulaDef, *, actor: str) -> FormulaDef:
    """name 为 None 时新建，否则修改名为 name 的公式（不是内置公式时可以改代号）。"""
    row, data, rules = await draft()
    formulas = list(data.formulas)
    taken = {f.name for f in formulas}
    if name is None:
        if formula.name in taken:
            raise GameError("invalid", f"已经有代号为 {formula.name} 的公式")
        formulas.append(formula)
        before, action = None, "create_formula"
    else:
        index = next((n for n, f in enumerate(formulas) if f.name == name), None)
        if index is None:
            raise GameError("not_found", f"没有公式 {name}")
        old = formulas[index]
        if name in REQUIRED_FORMULAS:
            if formula.name != name:
                raise GameError("invalid", "战斗计算要用的内置公式不能改代号")
            if list(formula.params) != list(old.params):
                raise GameError("invalid", "战斗计算要用的内置公式不能增删或改名变量（战斗按这些变量名传值），"
                                           f"变量必须是：{'、'.join(old.params)}")
        elif formula.name != name:
            if formula.name in taken:
                raise GameError("invalid", f"已经有代号为 {formula.name} 的公式")
            callers = [f.title or f.name for f in rules.formulas.values() if name in f.expr.calls]
            if callers:
                raise GameError("invalid", f"这些公式调用了它，不能改代号：{'、'.join(callers)}")
        formulas[index] = formula
        before, action = _dump(old), "edit_formula"
    await _commit(row, replace(data, formulas=formulas), ["formulas"], actor=actor, action=action,
                  target=f"公式 {formula.name}", before=before, after=_dump(formula))
    return formula


@serialized
async def delete_formula(name: str, *, actor: str) -> None:
    row, data, rules = await draft()
    old = next((f for f in data.formulas if f.name == name), None)
    if old is None:
        raise GameError("not_found", f"没有公式 {name}")
    if name in REQUIRED_FORMULAS:
        raise GameError("invalid", "战斗计算要用的内置公式不能删除")
    callers = [f.title or f.name for f in rules.formulas.values() if name in f.expr.calls]
    if callers:
        raise GameError("invalid", f"这些公式调用了它，不能删除：{'、'.join(callers)}")
    await _commit(row, replace(data, formulas=[f for f in data.formulas if f.name != name]), ["formulas"],
                  actor=actor, action="delete_formula", target=f"公式 {name}", before=_dump(old))


@serialized
async def save_setting(key: str, setting: SettingDef, *, actor: str) -> SettingDef:
    """只修改已定义的游戏设定，整个草稿通过校验才保存。"""
    from .game_defaults import DEFAULTS

    if key not in DEFAULTS or setting.key != key:
        raise GameError("invalid", "只能修改已有的游戏设定，不能更改代号")
    row, data, _ = await draft()
    old = next((s for s in data.settings if s.key == key), None)
    settings = [s for s in data.settings if s.key != key] + [setting]
    await _commit(row, replace(data, settings=settings), ["settings"], actor=actor,
                  action="edit_setting", target=f"设定 {key}", before=_dump(old), after=_dump(setting))
    return setting


@serialized
async def save_settings(changes: list[SettingDef], *, actor: str) -> list[SettingDef]:
    """年卡表单一次提交全部字段，一起校验和保存。"""
    from .game_defaults import DEFAULTS

    keys = {s.key for s in changes}
    if not changes or len(changes) > len(DEFAULTS) or len(keys) != len(changes) or not keys <= DEFAULTS.keys():
        raise GameError('invalid', '设定不能为空、重复或包含未知代号')
    row, data, _ = await draft()
    before = [_dump(s) for s in data.settings if s.key in keys]
    settings = [s for s in data.settings if s.key not in keys] + changes
    await _commit(row, replace(data, settings=settings), ['settings'], actor=actor,
                  action='edit_settings', target='游戏设定', before=before, after=[_dump(s) for s in changes])
    return changes


# ---------------------------------------------------------------- 游戏里直接改规则（定制宝石）


@serialized
async def apply_to_live(mutate: Callable[[RuleData], RuleData], *, actor: str, note: str) -> int:
    """游戏指令需要马上改规则时用（例如超管做一颗定制宝石要新增一件装备）：
    在当前生效版本上改好，存成新版本并立即激活；有草稿时草稿里也做同样的修改，激活草稿时不会丢掉。"""
    global _draft
    active = await active_version_id()
    if active is None:
        raise GameError("not_found", "还没有生效的规则版本")
    data = mutate(await frozen_data(active))
    _compile(data, None)
    version_id = await save_version(data, actor=actor, note=note, activate=True, parent_id=active)
    _frozen[version_id] = data
    row = await draft_row()
    if row is not None:
        draft_data = mutate(await load_data(row.id))
        await _commit(row, draft_data, [f.name for f in fields(RuleData)], actor=actor, action="sync",
                      target=note)
    await current.reload()
    return version_id


# ---------------------------------------------------------------- 对比


def _key(category: str, obj: Any) -> str:
    return str(getattr(obj, _KEY_FIELD.get(category, "id")))


def _show(value: Any) -> str:
    if value is None or value == "":
        return "无"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _details(category: str, old: dict, new: dict, rules: RuleSet | None) -> list[str]:
    out: list[str] = []
    for field in sorted(set(old) | set(new), key=lambda f: (f not in FIELD_LABELS, f)):
        a, b = old.get(field), new.get(field)
        if a == b:
            continue
        label = FIELD_LABELS.get(field, field)
        if isinstance(a, dict) or isinstance(b, dict):
            a, b = a or {}, b or {}
            for k in sorted(set(a) | set(b)):
                if a.get(k) != b.get(k):
                    name = rules.stats[k].name if category == "items" and rules and k in rules.stats else k
                    out.append(f"{label} · {name}：{_show(a.get(k))} → {_show(b.get(k))}")
        elif isinstance(a, (str, int, float, bool)) or isinstance(b, (str, int, float, bool)) or a is None or b is None:
            out.append(f"{label}：{_show(a)} → {_show(b)}")
        else:
            out.append(f"{label}有改动")
    return out


def diff(old: RuleData | None, new: RuleData, rules: RuleSet | None = None) -> list[DiffEntry]:
    entries: list[DiffEntry] = []
    for f in fields(RuleData):
        before = {_key(f.name, x): x for x in (getattr(old, f.name) if old else [])}
        after = {_key(f.name, x): x for x in getattr(new, f.name)}
        label = CATEGORY_LABELS.get(f.name, f.name)

        def name_of(obj: Any, category: str = f.name) -> str:
            return getattr(obj, "title", "") or getattr(obj, "name", "") or _key(category, obj)

        for key, obj in after.items():
            if key not in before:
                entries.append(DiffEntry(category=f.name, category_label=label, key=key, name=name_of(obj),
                                         change="added"))
            elif _dump(obj) != _dump(before[key]):
                entries.append(DiffEntry(category=f.name, category_label=label, key=key, name=name_of(obj),
                                         change="changed",
                                         details=_details(f.name, _dump(before[key]), _dump(obj), rules)))
        for key, obj in before.items():
            if key not in after:
                entries.append(DiffEntry(category=f.name, category_label=label, key=key, name=name_of(obj),
                                         change="removed"))
    return entries


async def draft_diff() -> list[DiffEntry]:
    row, data, rules = await draft()
    return diff(await parent_of(row), data, rules)


async def item_marks() -> tuple[set[int], set[int]]:
    """草稿里改过的装备、新建的装备（卡片上的标记）。"""
    changed: set[int] = set()
    added: set[int] = set()
    for entry in await draft_diff():
        if entry.category == "items":
            (added if entry.change == "added" else changed).add(int(entry.key))
    return changed, added


# ---------------------------------------------------------------- 校验、激活、回滚

_BASE = {"hp": 3000, "atk": 300, "defense": 80, "agi": 60, "mp": 300}
_DUMMY = MonsterDef(id="__selftest__", name="自检木桩", kind="boss", level=60,
                    stats={"hp": 20000, "atk": 400, "defense": 150, "magic_resist": 80, "agi": 40})
MAX_PROBLEMS = 30


def self_test(rules: RuleSet) -> tuple[list[str], int]:
    """套装、装备、尚未关联的效果及全部怪物，固定种子试战，捕获运行错误。"""
    monsters: list[MonsterDef] = []
    for kind in ("normal", "boss"):
        pool = sorted((m for m in rules.monsters.values() if m.kind == kind), key=lambda m: (m.level, m.id))
        if pool:
            monsters.append(pool[len(pool) // 2])
            if kind == "boss" and pool[-1] is not monsters[-1]:
                monsters.append(pool[-1])         # 最高等级的 BOSS 能打很多回合，触发更多效果
    monsters = monsters or [_DUMMY]
    cases: list[tuple[str, list[ItemDef], list[Any]]] = []
    for name, spec in rules.sets.items():
        members = [i for i in rules.items.values() if name in i.sets][:6]
        own = [e for i in members for e in i.effects]
        for tier in spec.tiers:
            cases.append((f"套装「{name}」{tier.pieces} 件", members, rules.set_effects({name: tier.pieces}) + own))
    for item in rules.items.values():
        if item.effects:
            cases.append((f"装备「{item.name}」", [item], list(item.effects)))
    covered = {e for _, _, effects in cases for e in effects}
    for effect in rules.effects.values():
        if effect.id not in covered:
            cases.append((f"效果「{effect.name}」", [], [effect.id]))
    problems: list[str] = []
    battles = 0
    for label, members, effects in cases:
        weapon = next((i for i in members if i.slot == "weapon"), None)
        base = dict(_BASE)
        for member in members:
            for k, v in member.stats.items():
                base[k] = base.get(k, 0) + v
        for monster in monsters:
            battles += 1
            try:
                player = build_player(rules, level=60, base=base, effects=effects,
                                      damage_type=(weapon.damage_type if weapon else None) or "physical",
                                      weapon_id=str(weapon.id) if weapon else "")
                fight(rules, player, build_monster(rules, monster), seed=battles)
            except Exception as exc:     # noqa: BLE001 —— 自检就是要把任何出错都报出来
                problems.append(f"{label}打「{monster.name}」时出错：{exc}")
                break
        if len(problems) >= MAX_PROBLEMS:
            problems.append(f"问题太多，只列出前 {MAX_PROBLEMS} 个")
            break
    if len(problems) < MAX_PROBLEMS:
        for monster in rules.monsters.values():
            battles += 1
            try:
                fight(rules, build_player(rules, level=60, base=dict(_BASE)),
                      build_monster(rules, monster), seed=battles)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"怪物「{monster.name}」试战出错：{exc}")
            if len(problems) >= MAX_PROBLEMS:
                break
    return problems, battles


async def validate() -> ValidateResult:
    from .management import validate as validate_business

    _, data, _ = await draft()
    try:
        validate_business(data)
        rules = data.compile()
    except RuleError as exc:
        return ValidateResult(ok=False, problems=exc.problems)
    except GameError as exc:
        return ValidateResult(ok=False, problems=exc.detail.get("problems", [str(exc)]))
    problems, battles = await asyncio.to_thread(self_test, rules)
    return ValidateResult(ok=not problems, problems=problems, battles=battles)


@serialized
async def activate_draft(*, actor: str) -> RuleVersionInfo:
    global _draft
    row, data, _ = await draft()
    result = await validate()
    if not result.ok:
        raise GameError("rules_invalid", "校验没有通过，不能激活：" + result.problems[0], problems=result.problems)
    await activate_version(row.id, actor=actor)
    _frozen[row.id] = data
    _draft = None
    await current.reload()
    return info(await RuleVersion.get(id=row.id))


@serialized
async def rollback(version_id: int, *, actor: str) -> RuleVersionInfo:
    row = await RuleVersion.get_or_none(id=version_id)
    if row is None or row.status != ARCHIVED:
        raise GameError("invalid", "只能回滚到已归档的版本")
    await activate_version(version_id, actor=actor)
    await RuleAudit.create(version=row, actor=actor, action="rollback", target=f"版本 {version_id}")
    await current.reload()
    return info(await RuleVersion.get(id=version_id))


async def versions() -> list[RuleVersionInfo]:
    return [info(r) for r in await RuleVersion.all().order_by("-id")]


async def state() -> dict[str, Any]:
    active = await RuleVersion.filter(status=ACTIVE).order_by("-id").first()
    row = await draft_row()
    changes = len(await draft_diff()) if row else 0
    return {"active": info(active) if active else None, "draft": info(row) if row else None, "changes": changes}
