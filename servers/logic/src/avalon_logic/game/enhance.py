"""强化、淬炼（对应旧版 db.enhance_equipped / temper_equipped，以及背包插件"强化""淬炼"指令里的判定）。

强化：10 级前必定成功，10 级起按成功率逐级判定，某一级失败就停在那一级；
强化祝福符加成功率，强化保护符失败时返还失败那一级费用的一部分，强化奇迹符成功时有概率再升 1 级。
淬炼：5 本及以上副本的装备，消耗这个副本的隐秘宝石 1 颗和代币，基础属性 +1~5%，上限 +10%。
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from . import bag, core, economy, info, props, tuning
from .constants import ENHANCE_CHARM_EFFECTS, EQUIP_SLOT_LABELS
from .results import EnhanceResult, TemperResult


def _bad_cost(c: object) -> bool:
    return not isinstance(c, int) or isinstance(c, bool) or c <= 0


async def enhance_equipped(openid: str, slot: str, costs: int | list[int], new_level: int | None = None,
                           failed_at: int | None = None, protect_pct: int = 0) -> EnhanceResult:
    """扣代币、写入新的强化等级（判定已经由调用方做好）。"""
    if slot not in EQUIP_SLOT_LABELS:
        return EnhanceResult(ok=False, error="bad_slot")
    steps = [costs] if isinstance(costs, int) else list(costs)
    if not steps or any(_bad_cost(c) for c in steps):
        return EnhanceResult(ok=False, error="bad_qty", slot=slot)
    total = sum(steps)
    async with core.tx():
        e = await bag._worn(openid, slot)
        if e is None:
            return EnhanceResult(ok=False, error="no_user", slot=slot)
        if e.item_id is None:
            return EnhanceResult(ok=False, error="empty", slot=slot)
        name, level = core.item_name(e.item_id), e.enhance
        if slot == "gem":
            return EnhanceResult(ok=False, error="not_enhanceable", slot=slot, name=name)
        target = level + len(steps) if new_level is None else new_level
        if target < level:
            return EnhanceResult(ok=False, error="bad_qty", slot=slot, name=name, old_level=level)
        balance = int((await core.wallet(openid)).coins)
        if balance < total:
            return EnhanceResult(ok=False, error="no_coins", slot=slot, name=name, old_level=level, cost=total,
                                 coins=balance)
        refund = 0
        if failed_at is not None and 0 < protect_pct <= 100:     # 强化保护符
            refund = info.enhance_step_cost(failed_at) * protect_pct // 100
        coins = await economy._add_coins(openid, refund - total)
        e.enhance = target
        await e.save(update_fields=["enhance"])
        return EnhanceResult(ok=True, slot=slot, name=name, old_level=level, new_level=target, cost=total, coins=coins,
                             failed_at=failed_at, refund=refund)


@core.rollback_result
async def temper_equipped(openid: str, slot: str, gem_name: str, cost: int, added: int) -> TemperResult:
    """消耗隐秘宝石 1 颗和代币，淬炼度 +added（上限 10%）。淬炼度跟着装备走，卸下时回到对应的背包格。"""
    if slot not in EQUIP_SLOT_LABELS:
        return TemperResult(ok=False, error="bad_slot")
    if slot == "gem":
        return TemperResult(ok=False, error="not_temperable", slot=slot)
    if _bad_cost(cost):
        return TemperResult(ok=False, error="bad_cost", slot=slot)
    if _bad_cost(added):
        return TemperResult(ok=False, error="bad_qty", slot=slot)
    async with core.tx():
        e = await bag._worn(openid, slot)
        if e is None:
            return TemperResult(ok=False, error="no_user", slot=slot)
        if e.item_id is None:
            return TemperResult(ok=False, error="empty", slot=slot)
        name, level, old = core.item_name(e.item_id), e.enhance, e.temper
        if old >= tuning.value('temper_cap_pct'):
            return TemperResult(ok=False, error="capped", slot=slot, name=name, enhance=level, temper=old)
        error, _ = await bag._take(openid, gem_name, 1)
        if error:
            raise core.Rollback(TemperResult(ok=False, error="no_gem" if error == "not_enough" else error, slot=slot,
                                             name=name, enhance=level, temper=old))
        balance = int((await core.wallet(openid)).coins)
        if balance < cost:
            raise core.Rollback(TemperResult(ok=False, error="no_coins", slot=slot, name=name, enhance=level,
                                             temper=old, cost=cost, coins=balance))
        new = min(tuning.value('temper_cap_pct'), old + added)
        coins = await economy._add_coins(openid, -cost)
        e.temper = new
        await e.save(update_fields=["temper"])
        return TemperResult(ok=True, slot=slot, name=name, enhance=level, temper=new, added=new - old, cost=cost,
                            coins=coins)


# ---------------------------------------------------------------- 指令里的判定（原来写在背包插件里）


@dataclass(frozen=True)
class EnhancePreview:
    """+10 起单级强化的确认信息：成功率（含祝福符）和花费。"""

    name: str
    level: int
    chance: float
    cost: int


async def enhance_preview(openid: str, slot: str) -> EnhancePreview | None:
    worn = await bag.get_equipped(openid, slot)
    if worn is None:
        return None
    name, level, _ = worn
    charms = await props.peek_prop_buffs(openid, ENHANCE_CHARM_EFFECTS)
    bless = charms.get("enhance_bless", (0, ""))[0]
    return EnhancePreview(name=name, level=level, chance=min(1.0, info.enhance_success_chance(level) + bless / 100),
                          cost=info.enhance_step_cost(level))


@core.atomic
async def enhance(openid: str, slot: str, target: int | None = None) -> EnhanceResult:
    """强化到 target 级（不写就是 +1）：逐级判定，用上待生效的强化符咒，成功扣费后清掉符咒。"""
    worn = await bag.get_equipped(openid, slot)
    if worn is None:
        return EnhanceResult(ok=False, error="empty" if await economy.user_exists(openid) else "no_user", slot=slot)
    _, level, _ = worn
    target = level + 1 if target is None else target
    if target <= level:
        return EnhanceResult(ok=False, error="bad_qty", slot=slot, old_level=level)
    charms = await props.peek_prop_buffs(openid, ENHANCE_CHARM_EFFECTS)
    bless = charms.get("enhance_bless", (0, ""))[0]
    protect = charms.get("enhance_protect", (0, ""))[0]
    miracle = charms.get("enhance_miracle", (0, ""))[0]
    if bless > 0:
        def roll(lv: int) -> bool:
            return random.random() < min(1.0, info.enhance_success_chance(lv) + bless / 100)
    else:
        roll = info.attempt_enhance
    new_level, spent, failed_at = info.enhance_progress(level, target, roll)
    if failed_at is None and miracle > 0 and random.random() * 100 < miracle:
        new_level += 1           # 强化奇迹符
    result = await enhance_equipped(openid, slot, spent, new_level, failed_at, protect_pct=protect)
    if result.ok:
        await props.clear_prop_buffs(openid, ENHANCE_CHARM_EFFECTS)
    return result


@dataclass(frozen=True)
class TemperPlan:
    gem: str = ""
    baseline: int = 0
    cost: int = 0
    error: str = ""              # low_dungeon（5 本以下）/ no_gem_config（副本没有隐秘宝石）


def temper_plan(name: str) -> TemperPlan:
    dungeon = info.item_dungeon_id(name)
    if dungeon < tuning.value('temper_base_dungeon'):
        return TemperPlan(error="low_dungeon")
    gem = info.dungeon_hidden_gem(dungeon)
    if not gem:
        return TemperPlan(error="no_gem_config")
    crafted = info.is_crafted_item(name)
    return TemperPlan(gem=gem, baseline=info.temper_baseline_level(dungeon, crafted),
                      cost=info.temper_coin_cost(dungeon, crafted))


@core.atomic
async def temper(openid: str, slot: str) -> tuple[TemperResult, TemperPlan]:
    """淬炼身上这件装备：检查副本门槛，随机 +1~5%。"""
    worn = await bag.get_equipped(openid, slot)
    if worn is None:
        error = "empty" if await economy.user_exists(openid) else "no_user"
        return TemperResult(ok=False, error=error, slot=slot), TemperPlan()
    name, level, current = worn
    if current >= tuning.value('temper_cap_pct'):
        return TemperResult(ok=False, error="capped", slot=slot, name=name, enhance=level, temper=current), TemperPlan()
    plan = temper_plan(name)
    if plan.error:
        return TemperResult(ok=False, error=plan.error, slot=slot, name=name, enhance=level, temper=current), plan
    added = random.randint(tuning.value('temper_roll_min'), tuning.value('temper_roll_max'))
    return await temper_equipped(openid, slot, plan.gem, plan.cost, added), plan
