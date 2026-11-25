"""完整规则管理：引用检查、草稿并发保护、预检和审计；不写玩家数据库。"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import replace
from typing import Any

from avalon_contracts.api.rules_manage import (
    RuleCategory,
    RuleDelete,
    RuleRecord,
    RuleRecords,
    RuleWrite,
)
from avalon_contracts.errors import GameError
from avalon_contracts.rules.effect import (
    ACTIONS,
    BATTLE_OPS,
    STATIC_OPS,
    TRIGGERS,
    ActionSpec,
    EffectDef,
)
from avalon_contracts.rules.item import SetDef
from avalon_contracts.rules.monster import KIND_LABELS, DungeonDef, MonsterDef, Reward
from avalon_contracts.rules.prop import PropDef, RecipeDef
from avalon_contracts.rules.stack import StackDef
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..engine.ruleset import IMPLEMENTED_ACTIONS, IMPLEMENTED_TRIGGERS
from ..store.models.rules import PropRow, RuleVersion
from . import editing
from .action_fields import check_action
from .locking import serialized
from .store import RuleData, active_version_id


class Drops(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rewards: list[Reward] = Field(default_factory=list)
    prop_rewards: list[Reward] = Field(default_factory=list)
    info_rewards: list[str] = Field(default_factory=list)


MODELS: dict[str, type[BaseModel]] = {
    "effects": EffectDef, "sets": SetDef, "monsters": MonsterDef, "dungeons": DungeonDef,
    "drops": Drops, "props": PropDef, "recipes": RecipeDef, "prop_recipes": RecipeDef, "stacks": StackDef,
}
LABELS = {**editing.CATEGORY_LABELS, "drops": "掉落"}
PROP_EFFECTS = {
    "material": "材料", "fragment": "碎片", "box": "随机资源礼盒", "stamina": "恢复体力",
    "exp": "增加经验", "coins": "增加代币", "equip": "副本装备礼盒", "boss_choice": "BOSS 装备自选",
    "box_strengthen": "强化道具礼盒", "box_dungeon": "副本道具礼盒", "exp_pct": "升级经验百分比",
    "enhance_bless": "强化成功率加成", "enhance_protect": "强化失败返还", "enhance_miracle": "额外强化一级",
    "dungeon_lure": "诱怪", "dungeon_cross": "跨界挑战", "dungeon_repeat": "重复挑战",
    "dungeon_double": "双倍掉落", "dungeon_lucky": "幸运", "dungeon_lifesteal": "吸血",
    "dungeon_combo": "连击", "dungeon_exp_bonus": "副本经验加成", "dungeon_coin_bonus": "副本代币加成",
    "makeup_checkin": "补签",
}


def document(obj: BaseModel) -> dict:
    return obj.model_dump(mode="json", by_alias=True, exclude_none=True)


def fingerprint(obj: BaseModel) -> str:
    return hashlib.sha256(json.dumps(document(obj), sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def key_of(category: str, obj: BaseModel) -> str:
    return str(getattr(obj, "name" if category == "sets" else "key" if category == "stacks" else "id"))


def _category(category: str) -> str:
    return "monsters" if category == "drops" else category


def _find(data: RuleData, category: str, key: str) -> BaseModel:
    found = next((x for x in getattr(data, _category(category)) if key_of(category, x) == key), None)
    if found is None:
        raise GameError("not_found", f"{LABELS[category]}「{key}」不存在，请刷新列表")
    return found


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def references(data: RuleData, category: str, obj: BaseModel) -> list[str]:
    """用于显示引用位置，并在改名或删除时给出可处理的提示。"""
    out: list[str] = []
    key = key_of(category, obj)
    if category == "effects":
        out += [f"装备：{x.name}" for x in data.items if key in x.effects]
        out += [f"套装：{x.name} · {t.pieces} 件" for x in data.sets for t in x.tiers if key in t.effects]
        out += [f"怪物：{x.name}" for x in data.monsters if key in x.effects]
        out += [f"设定：{x.key}" for x in data.settings if x.key == "global_effects" and key in x.value]
        for effect in data.effects:
            if effect.id == key:
                continue
            if any(key == s or re.search(r"\b(?:hit|dealt)\.by\." + re.escape(key) + r"\b", s)
                   for s in _strings(document(effect))):
                out.append(f"效果：{effect.name}")
    elif category == "sets":
        out += [f"装备：{x.name}" for x in data.items if key in x.sets]
    elif category == "monsters":
        out += [f"副本：{x.name}" for x in data.dungeons
                if x.hidden_id == key or any(e.monster_id == key for e in x.encounters)]
        out += [f"道具：{x.name}" for x in data.props if x.effect == "boss_choice" and x.dungeon == obj.name]
    elif category == "dungeons":
        out += [f"道具：{x.name}" for x in data.props if x.effect == "equip" and x.dungeon == obj.name]
    elif category == "props":
        name = obj.name
        out += [f"怪物掉落：{x.name}" for x in data.monsters if any(r.name == name for r in x.prop_rewards)]
        out += [f"{label}：{x.output}" for label, group in (("配方", data.recipes), ("道具配方", data.prop_recipes))
                for x in group if x.output == name or any(i.name == name for i in x.inputs)]
        out += [f"设定：{x.key}" for x in data.settings if name in set(_strings(x.value))]
    elif category == "stacks":
        pattern = re.compile(r"\.stacks\." + re.escape(key) + r"(?:\b|$)")
        out += [f"效果：{x.name}" for x in data.effects
                if any(key == s or pattern.search(s) for s in _strings(document(x)))]
    return sorted(set(out))


async def _published_props() -> set[int]:
    # 回滚后也不能删除曾经发布过的道具，否则已有仓库记录失去定义。
    versions = await RuleVersion.filter(status__in=["active", "archived"]).values_list("id", flat=True)
    return set(await PropRow.filter(version_id__in=versions).values_list("prop_id", flat=True))


def record(data: RuleData, category: str, obj: BaseModel, protected_props: set[int]) -> RuleRecord:
    raw = document(obj)
    if category == "drops":
        raw = {k: raw[k] for k in ("rewards", "prop_rewards", "info_rewards")}
    name = getattr(obj, "name", None) or getattr(obj, "output", None) or key_of(category, obj)
    summary = ""
    if category == "effects":
        summary = obj.render_desc()
    elif category == "sets":
        summary = " / ".join(f"{t.pieces} 件：{len(t.effects)} 个效果" for t in obj.tiers)
    elif category == "monsters":
        summary = f"{KIND_LABELS[obj.kind]} · Lv.{obj.level} · {len(obj.effects)} 个效果"
    elif category == "drops":
        summary = f"装备 {len(obj.rewards)} / 道具 {len(obj.prop_rewards)} / 归属 {len(obj.info_rewards)}"
    elif category == "dungeons":
        summary = f"体力 {obj.stamina} · {len(obj.encounters)} 种遇怪"
    elif category == "props":
        summary = obj.blurb or PROP_EFFECTS.get(obj.effect, obj.effect)
    elif category in {"recipes", "prop_recipes"}:
        summary = " + ".join(f"{i.name} × {i.quantity}" for i in obj.inputs) + f" → {obj.quantity} 个"
    elif category == "stacks":
        summary = f"上限：{obj.max if obj.max is not None else '不限'}"
    protected = "曾经发布的道具可能仍在玩家仓库中，不能删除" if category == "props" and obj.id in protected_props else ""
    if category == "drops":
        protected = "掉落属于怪物，可编辑或清空掉落列表"
    return RuleRecord(key=key_of(category, obj), name=name, summary=summary, data=raw, hash=fingerprint(obj),
                      references=references(data, category, obj), protected_reason=protected)


async def pick(use_draft: bool) -> tuple[int, RuleData, bool]:
    if use_draft and await editing.draft_row() is not None:
        row, data, _ = await editing.draft()
        return row.id, data, True
    version = await active_version_id()
    if version is None:
        raise GameError("not_found", "还没有生效的规则版本")
    return version, await editing.frozen_data(version), False


async def listing(category: RuleCategory, use_draft: bool) -> RuleRecords:
    version, data, is_draft = await pick(use_draft)
    protected = await _published_props() if category == "props" else set()
    return RuleRecords(version_id=version, draft=is_draft,
                       records=[record(data, category, x, protected) for x in getattr(data, _category(category))])


async def meta(use_draft: bool) -> dict:
    version, data, is_draft = await pick(use_draft)
    published_props = await _published_props()
    return {
        "version_id": version, "draft": is_draft,
        "stats": [{"key": x.key, "name": x.name, "percent": x.percent} for x in data.stats],
        "effects": [{"key": x.id, "name": x.name} for x in data.effects],
        "sets": [{"key": x.name, "name": x.name} for x in data.sets],
        "monsters": [{"key": x.id, "name": x.name, "kind": x.kind} for x in data.monsters],
        "dungeons": [{"key": str(x.id), "name": x.name} for x in data.dungeons],
        "items": [{"key": x.name, "name": x.name} for x in data.items],
        "props": [{"key": x.name, "name": x.name} for x in data.props],
        "stacks": [{"key": x.key, "name": x.name} for x in data.stacks],
        "triggers": {k: v for k, v in TRIGGERS.items() if k in IMPLEMENTED_TRIGGERS},
        "actions": {k: v for k, v in ACTIONS.items() if k in IMPLEMENTED_ACTIONS},
        "static_ops": STATIC_OPS, "battle_ops": BATTLE_OPS, "kinds": KIND_LABELS, "prop_effects": PROP_EFFECTS,
        "schemas": {k: v.model_json_schema(by_alias=True) for k, v in MODELS.items()},
        "next_ids": {k: max([x.id for x in getattr(data, k)] + (list(published_props) if k == "props" else []), default=0) + 1
                     for k in ("dungeons", "props", "recipes", "prop_recipes")},
    }


def _finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise GameError("invalid", "数值必须是有限数字")
    if isinstance(value, (dict, list)):
        for item in value.values() if isinstance(value, dict) else value:
            _finite(item)


def _unknown(raw: Any, parsed: Any, path: str = "") -> None:
    """普通模型拒绝拼错的字段，动作保留引擎的可扩展参数。"""
    if isinstance(parsed, BaseModel) and isinstance(raw, dict):
        if isinstance(parsed, ActionSpec):
            check_action(parsed, path)
        fields = type(parsed).model_fields
        known = {k for k in fields} | {f.alias for f in fields.values() if f.alias}
        if not isinstance(parsed, ActionSpec) and (extra := set(raw) - known):
            raise GameError("invalid", f"{path or '规则'} 包含未知字段：{'、'.join(sorted(extra))}")
        for name, field in fields.items():
            key = field.alias if field.alias in raw else name
            if key in raw:
                _unknown(raw[key], getattr(parsed, name), f"{path}.{key}".lstrip("."))
    elif isinstance(parsed, list) and isinstance(raw, list):
        for i, (r, p) in enumerate(zip(raw, parsed, strict=True)):
            _unknown(r, p, f"{path}[{i + 1}]")


def parse(category: RuleCategory, raw: dict) -> BaseModel:
    _finite(raw)
    if len(json.dumps(raw, ensure_ascii=False)) > 200_000:
        raise GameError("invalid", "单条规则过大，请拆分效果")
    try:
        obj = MODELS[category].model_validate(raw)
    except ValidationError as exc:
        problems = [f"{'.'.join(str(p) for p in e['loc'])}：{e['msg']}" for e in exc.errors(include_input=False)]
        raise GameError("invalid", "规则字段不正确", problems=problems) from exc
    _unknown(raw, obj)
    for field in ("name", "output", "id", "key"):
        value = getattr(obj, field, None)
        if isinstance(value, str) and (not value.strip() or value != value.strip() or len(value) > 64 or "/" in value):
            raise GameError("invalid", f"{field} 须为 1～64 个字符，不能带首尾空格或斜杠")
    return obj


def validate(data: RuleData) -> None:
    """编辑器补充业务约束；整份编译仍由 _commit 执行。"""
    problems: list[str] = []
    def unique(values, label):
        seq = list(values)
        if len(seq) != len(set(seq)):
            problems.append(f"{label}不能重复")
    for category in ("effects", "sets", "monsters", "dungeons", "props", "recipes", "prop_recipes", "stacks"):
        values = getattr(data, category)
        unique((key_of(category, x) for x in values), f"{LABELS[category]}编号/代号")
        if category in {"monsters", "dungeons", "props"}:
            unique((x.name for x in values), f"{LABELS[category]}名称")
    items = {x.name for x in data.items}
    props = {x.name for x in data.props}
    for spec in data.sets:
        unique((t.pieces for t in spec.tiers), f"套装「{spec.name}」件数档位")
        for tier in spec.tiers:
            unique(tier.effects, f"套装「{spec.name}」{tier.pieces} 件效果")
    for monster in data.monsters:
        if monster.coins < 0 or monster.exp < 0 or (monster.no is not None and monster.no < 0):
            problems.append(f"怪物「{monster.name}」奖励和图鉴编号不能为负")
        for rewards, names, label in ((monster.rewards, items, "装备掉落"), (monster.prop_rewards, props, "道具掉落")):
            unique((r.name for r in rewards), f"怪物「{monster.name}」{label}")
            for reward in rewards:
                if reward.name not in names:
                    problems.append(f"怪物「{monster.name}」{label}引用不存在的名称：{reward.name}")
        for name in monster.info_rewards:
            if name not in items:
                problems.append(f"怪物「{monster.name}」归属装备不存在：{name}")
    unique((m.no for m in data.monsters if m.no is not None), "怪物图鉴编号")
    for dungeon in data.dungeons:
        unique((x.monster_id for x in dungeon.encounters), f"副本「{dungeon.name}」遇怪")
        if not dungeon.encounters or sum(x.weight for x in dungeon.encounters) <= 0:
            problems.append(f"副本「{dungeon.name}」至少需要一种权重大于 0 的遇怪")
    for label, group, names in (("装备配方", data.recipes, items), ("道具配方", data.prop_recipes, props)):
        unique((r.output for r in group), f"{label}成品")
        for recipe in group:
            unique((i.name for i in recipe.inputs), f"{label}「{recipe.output}」材料")
            for name in (recipe.output, *(i.name for i in recipe.inputs)):
                if name not in names:
                    problems.append(f"{label}「{recipe.output}」引用不属于此类别的物品：{name}")
    dungeon_names = {x.name for x in data.dungeons}
    boss_names = {x.name for x in data.monsters if x.kind == "boss"}
    for prop in data.props:
        if prop.effect not in PROP_EFFECTS or prop.amount < 0 or prop.value < 0:
            problems.append(f"道具「{prop.name}」效果未知或数值为负")
        if prop.effect in {"equip", "boss_choice"} and prop.dungeon not in (dungeon_names if prop.effect == "equip" else boss_names):
            problems.append(f"道具「{prop.name}」须选择存在的{'副本' if prop.effect == 'equip' else 'BOSS'}")
    for stack in data.stacks:
        if stack.max is not None and stack.max < 1:
            problems.append(f"层数「{stack.name}」上限必须为正整数或不设上限")
    if problems:
        raise GameError("rules_invalid", "改动没有保存：" + problems[0], problems=problems)


async def _prepare(category: RuleCategory, key: str | None, body: RuleWrite | RuleDelete):
    row, data, _ = await editing.draft()
    if row.id != body.version_id:
        raise GameError("rules_conflict", "草稿已切换，请关闭编辑窗口并刷新列表")
    old = _find(data, category, key) if key is not None else None
    if old is not None and body.before_hash != fingerprint(old):
        raise GameError("rules_conflict", "这条规则已被修改，请刷新后重新编辑；当前输入尚未保存")
    if old is None and body.before_hash is not None:
        raise GameError("invalid", "新建规则不能携带旧记录的校验值")
    return row, data, old


async def _candidate(category: RuleCategory, key: str | None, body: RuleWrite):
    row, data, old = await _prepare(category, key, body)
    value = parse(category, body.data)
    actual = _category(category)
    if category == "drops":
        if old is None:
            raise GameError("invalid", "先新建怪物，再设置它的掉落")
        value = old.model_copy(update={k: getattr(value, k) for k in type(value).model_fields})
    if old is not None and category != "sets" and key_of(category, value) != key:
        raise GameError("invalid", "已有规则的编号/代号不能修改，请新建规则后调整引用")
    values = list(getattr(data, actual))
    if old is None:
        if any(key_of(category, x) == key_of(category, value) for x in values):
            raise GameError("rules_conflict", "编号/代号已被使用，请刷新后选择其他编号")
        if category == "props" and value.id in await _published_props():
            raise GameError("invalid", "该道具编号曾被发布，不能重新分配给其他道具")
        values.append(value)
    else:
        if category in {"props", "monsters", "dungeons"} and old.name != value.name:
            refs = references(data, category, old)
            if category == "monsters":
                refs = [r for r in refs if r.startswith("道具：")]
            if refs:
                raise GameError("rules_invalid", "改名前请先解除引用", problems=refs)
        values = [value if key_of(category, x) == key else x for x in values]
    candidate = replace(data, **{actual: values})
    if category == "sets" and old is not None and old.name != value.name:
        # 套装以名称作为主键；改名时同步更新所有装备，不能留下断开的关联。
        candidate = replace(candidate, items=[
            item.model_copy(update={"sets": [value.name if name == old.name else name for name in item.sets]})
            for item in data.items
        ])
    validate(candidate)
    return row, candidate, old, value


@serialized
async def save(category: RuleCategory, key: str | None, body: RuleWrite, *, actor: str, check_only: bool = False):
    row, data, old, value = await _candidate(category, key, body)
    if check_only:
        rules = editing._compile(data, row.id)
        normalized = document(value)
        if category == "drops":
            normalized = {k: normalized[k] for k in ("rewards", "prop_rewards", "info_rewards")}
        result = {"ok": True, "message": "字段、引用和表达式校验通过，尚未保存", "data": normalized}
        if category == "effects":
            from .views import effect_detail

            preview = effect_detail(rules, value)
            result["preview"] = {"description": preview.desc, "logic": preview.logic}
        return result
    categories = [_category(category)]
    if category == "sets" and old is not None and old.name != value.name:
        categories.append("items")
    await editing._commit(row, data, categories, actor=actor,
                          action=f"{'edit' if old is not None else 'create'}_{category}",
                          target=f"{LABELS[category]} {key_of(category, value)}",
                          before=document(old) if old is not None else None, after=document(value))
    return record(data, category, value, await _published_props() if category == "props" else set())


@serialized
async def remove(category: RuleCategory, key: str, body: RuleDelete, *, actor: str):
    row, data, old = await _prepare(category, key, body)
    info = record(data, category, old, await _published_props() if category == "props" else set())
    if info.protected_reason:
        raise GameError("invalid", info.protected_reason)
    if info.references:
        raise GameError("rules_invalid", "仍有其他规则引用它，请先解除引用", problems=info.references)
    candidate = replace(data, **{category: [x for x in getattr(data, category) if key_of(category, x) != key]})
    validate(candidate)
    await editing._commit(row, candidate, [category], actor=actor, action=f"delete_{category}",
                          target=f"{LABELS[category]} {key}", before=document(old))
