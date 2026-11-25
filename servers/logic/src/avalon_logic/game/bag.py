"""背包、穿戴、出售、分解、扩容、装备合成（对应旧版 db.py 的同名函数）。

背包按（装备、强化等级、淬炼度）分格；同一格最多 99 件；背包格数上限见 economy.max_item_kinds。
物品必须是规则库里有的装备或材料（旧版允许任意名字，新版不认识的名字返回 no_item）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from ..store.models.game import BagExpand, Equipped, InventoryItem, Player
from . import core, economy, info, tuning
from .constants import EQUIP_SLOT_KEYS, EQUIP_SLOT_LABELS, EQUIP_SLOTS
from .results import (
    AddItemResult,
    BagExpandResult,
    BatchSellResult,
    CraftResult,
    DecomposeResult,
    EquipResult,
    RemoveItemResult,
    SellLine,
    SellResult,
)

Row = tuple[str, int, int, int]       # （名称，数量，强化，淬炼）

_SLOT_ORDER = {key: idx for idx, key in enumerate(EQUIP_SLOT_LABELS)}


def format_item_name(name: str, enhance: int = 0) -> str:
    if not name or name == "无":
        return name or "无"
    return name if enhance <= 0 else f"{name} +{enhance}"


def parse_equip_slot(text: str) -> str | None:
    name = text.strip()
    if name in EQUIP_SLOT_KEYS:
        return EQUIP_SLOT_KEYS[name]
    return name if name in EQUIP_SLOT_LABELS else None


def slot_label(slot: str) -> str:
    return EQUIP_SLOT_LABELS.get(slot, slot)


def item_slot_label(name: str) -> str:
    return EQUIP_SLOT_LABELS.get(core.item_slot(name), "材料")


def _slot_rank(name: str) -> int:
    return _SLOT_ORDER.get(core.item_slot(name), len(_SLOT_ORDER))


def _bad_count(value: object) -> bool:
    return not isinstance(value, int) or isinstance(value, bool) or value <= 0


# ---------------------------------------------------------------- 读取


async def _rows(openid: str) -> list[InventoryItem]:
    """背包里的格子，按显示顺序：部位（武器…宝石、材料）→ 获得时间 → 先后。"""
    rows = await InventoryItem.filter(player_id=openid, quantity__gt=0)
    return sorted(rows, key=lambda r: (_slot_rank(core.item_name(r.item_id)), r.acquired_at, r.id))


def _view(r: InventoryItem) -> Row:
    return core.item_name(r.item_id), r.quantity, r.enhance, r.temper


async def list_inventory(openid: str) -> list[Row]:
    return [_view(r) for r in await _rows(openid)]


async def inventory_at(openid: str, index: int) -> Row | None:
    if _bad_count(index):
        return None
    rows = await list_inventory(openid)
    return rows[index - 1] if index <= len(rows) else None


async def _count(openid: str, item_id: int, enhance: int | None = None) -> int:
    q = InventoryItem.filter(player_id=openid, item_id=item_id, quantity__gt=0)
    if enhance is not None:
        q = q.filter(enhance=enhance)
    return sum(await q.values_list("quantity", flat=True))


async def inventory_count(openid: str, name: str, enhance: int | None = None) -> int:
    found = core.item_by_name(name)
    return 0 if found is None else await _count(openid, found.id, enhance)


async def sort_inventory(openid: str) -> list[Row] | None:
    """整理背包：按部位分类，部位内按装备编号升序；顺序写进获得时间，之后背包就按这个顺序显示。"""
    async with core.tx():
        if not await Player.exists(openid=openid):
            return None
        rows = await _rows(openid)
        ordered = sorted(rows, key=lambda r: (_slot_rank(core.item_name(r.item_id)), r.item_id))
        base = int(core.now())
        for pos, r in enumerate(ordered):
            r.acquired_at = datetime.fromtimestamp(base + pos).astimezone()
            await r.save(update_fields=["acquired_at"])
        return [_view(r) for r in ordered]


# ---------------------------------------------------------------- 放入、取出


async def _add(openid: str, name: str, quantity: int, enhance: int = 0, temper: int = 0) -> AddItemResult:
    if not await Player.exists(openid=openid):
        return AddItemResult(ok=False, error="no_user", name=name)
    found = core.item_by_name(name)
    if found is None:
        return AddItemResult(ok=False, error="no_item", name=name)
    held = await InventoryItem.get_or_none(player_id=openid, item_id=found.id, enhance=enhance, temper=temper)
    current = held.quantity if held else 0
    if held is None:
        kinds = await InventoryItem.filter(player_id=openid, quantity__gt=0).count()
        if kinds >= await economy.max_item_kinds(openid):
            return AddItemResult(ok=False, error="kinds_full", name=name, current=current)
    if current + quantity > tuning.value('max_stack'):
        return AddItemResult(ok=False, error="stack_full", name=name, current=current)
    if held is None:
        await InventoryItem.create(player_id=openid, item_id=found.id, enhance=enhance, temper=temper,
                                   quantity=quantity, acquired_at=datetime.fromtimestamp(int(core.now())).astimezone())
        new_qty = quantity
    else:
        held.quantity = new_qty = current + quantity
        await held.save(update_fields=["quantity"])
    return AddItemResult(ok=True, name=name, quantity=new_qty, current=current)


async def add_item(openid: str, name: str, quantity: int, enhance: int = 0) -> AddItemResult:
    name = name.strip()
    if not name:
        return AddItemResult(ok=False, error="bad_name")
    if _bad_count(quantity) or not isinstance(enhance, int) or enhance < 0:
        return AddItemResult(ok=False, error="bad_qty", name=name)
    async with core.tx():
        return await _add(openid, name, quantity, enhance)


async def _take(openid: str, name: str, quantity: int, enhance: int = 0,
                temper: int | None = 0) -> tuple[str | None, int]:
    """从（强化，淬炼）格里取 quantity 件。temper 为 None 时这个强化等级的所有格都可以取（淬炼低的先取）。
    返回（错误，这一格剩下的数量）。"""
    found = core.item_by_name(name)
    if found is None:
        return "no_item", 0
    if temper is None:
        rows = await InventoryItem.filter(player_id=openid, item_id=found.id, enhance=enhance,
                                          quantity__gt=0).order_by("temper")
        left = quantity
        for r in rows:
            take = min(left, r.quantity)
            error, _ = await _take(openid, name, take, enhance, r.temper)
            if error:
                return error, 0
            left -= take
            if left <= 0:
                return None, 0
        return "not_enough", 0
    held = await InventoryItem.get_or_none(player_id=openid, item_id=found.id, enhance=enhance, temper=temper)
    current = held.quantity if held else 0
    if held is None or current < quantity:
        return "not_enough", current
    remaining = current - quantity
    if remaining == 0:
        await held.delete()
    else:
        held.quantity = remaining
        await held.save(update_fields=["quantity"])
    return None, remaining


async def _take_any(openid: str, name: str, quantity: int, *, highest_first: bool = False) -> tuple[str | None, list[int]]:
    """不论强化等级取 quantity 件（默认强化低的先取），返回取走的每件的强化等级。"""
    found = core.item_by_name(name)
    if found is None:
        return "no_item", []
    order = ("-enhance" if highest_first else "enhance", "temper")
    rows = await InventoryItem.filter(player_id=openid, item_id=found.id, quantity__gt=0).order_by(*order)
    left = quantity
    taken: list[int] = []
    for r in rows:
        take = min(left, r.quantity)
        error, _ = await _take(openid, name, take, r.enhance, r.temper)
        if error:
            return error, taken
        taken.extend([r.enhance] * take)
        left -= take
        if left <= 0:
            return None, taken
    return "not_enough", taken


# ---------------------------------------------------------------- 穿戴


async def _worn(openid: str, slot: str) -> Equipped | None:
    if slot not in EQUIP_SLOT_LABELS or not await Player.exists(openid=openid):
        return None
    return (await core.equipped(openid))[slot]


def _clear(e: Equipped) -> None:
    e.item_id, e.enhance, e.temper = None, 0, 0


async def _matching_slots(openid: str, name: str, enhance: int | None = None) -> list[Equipped]:
    found = core.item_by_name(name)
    if found is None:
        return []
    eq = await core.equipped(openid)
    return [eq[s] for s in EQUIP_SLOTS if eq[s].item_id == found.id and (enhance is None or eq[s].enhance == enhance)]


async def get_equipped(openid: str, slot: str) -> tuple[str, int, int] | None:
    e = await _worn(openid, slot)
    if e is None or e.item_id is None:
        return None
    return core.item_name(e.item_id), e.enhance, e.temper


async def find_equipped_slot(openid: str, name: str) -> str | None:
    found = core.item_by_name(name)
    if found is None or not await Player.exists(openid=openid):
        return None
    eq = await core.equipped(openid)
    return next((s for s in EQUIP_SLOTS if eq[s].item_id == found.id), None)


@core.rollback_result
async def equip_item(openid: str, slot: str, name: str, enhance: int = 0, temper: int = 0) -> EquipResult:
    name = name.strip()
    if slot not in EQUIP_SLOT_LABELS:
        return EquipResult(ok=False, error="bad_slot", name=name, enhance=enhance)
    if not name:
        return EquipResult(ok=False, error="bad_name", slot=slot, enhance=enhance)
    if not isinstance(enhance, int) or enhance < 0 or not isinstance(temper, int) or temper < 0:
        return EquipResult(ok=False, error="bad_qty", slot=slot, name=name)
    async with core.tx():
        e = await _worn(openid, slot)
        if e is None:
            return EquipResult(ok=False, error="no_user", slot=slot, name=name, enhance=enhance)
        current = core.item_name(e.item_id) if e.item_id is not None else ""
        if current == name and e.enhance == enhance and e.temper == temper:
            return EquipResult(ok=False, error="already", slot=slot, name=name, enhance=enhance)
        error, _ = await _take(openid, name, 1, enhance, temper)
        if error:
            return EquipResult(ok=False, error=error, slot=slot, name=name, enhance=enhance)
        if current:
            added = await _add(openid, current, 1, e.enhance, e.temper)
            if not added.ok:
                raise core.Rollback(EquipResult(ok=False, error=added.error, slot=slot, name=name, enhance=enhance,
                                            replaced=current, replaced_enhance=e.enhance, current=added.current))
        replaced, replaced_enhance = current, e.enhance if current else 0
        found = core.item_by_name(name)
        e.item_id, e.enhance, e.temper = found.id, enhance, temper  # type: ignore[union-attr]
        await e.save()
        return EquipResult(ok=True, slot=slot, name=name, enhance=enhance, replaced=replaced,
                           replaced_enhance=replaced_enhance)


async def unequip_slot(openid: str, slot: str) -> EquipResult:
    if slot not in EQUIP_SLOT_LABELS:
        return EquipResult(ok=False, error="bad_slot")
    async with core.tx():
        e = await _worn(openid, slot)
        if e is None:
            return EquipResult(ok=False, error="no_user", slot=slot)
        if e.item_id is None:
            return EquipResult(ok=False, error="empty", slot=slot)
        name, enhance = core.item_name(e.item_id), e.enhance
        added = await _add(openid, name, 1, enhance, e.temper)
        if not added.ok:
            return EquipResult(ok=False, error=added.error, slot=slot, name=name, enhance=enhance, current=added.current)
        _clear(e)
        await e.save()
        return EquipResult(ok=True, slot=slot, name=name, enhance=enhance)


async def destroy_equipped(openid: str, slot: str) -> EquipResult:
    if slot not in EQUIP_SLOT_LABELS:
        return EquipResult(ok=False, error="bad_slot")
    async with core.tx():
        e = await _worn(openid, slot)
        if e is None:
            return EquipResult(ok=False, error="no_user", slot=slot)
        if e.item_id is None:
            return EquipResult(ok=False, error="empty", slot=slot)
        name, enhance = core.item_name(e.item_id), e.enhance
        _clear(e)
        await e.save()
        return EquipResult(ok=True, slot=slot, name=name, enhance=enhance)


@core.rollback_result
async def remove_item(openid: str, name: str, quantity: int | None = None, enhance: int | None = None) -> RemoveItemResult:
    """超管扣物品：先扣背包，不够再从身上脱下来扣掉。"""
    name = name.strip()
    if not name:
        return RemoveItemResult(ok=False, error="bad_name")
    if (quantity is not None and _bad_count(quantity)) or (enhance is not None and (not isinstance(enhance, int) or enhance < 0)):
        return RemoveItemResult(ok=False, error="bad_qty", name=name, enhance=enhance)
    async with core.tx():
        if not await Player.exists(openid=openid):
            return RemoveItemResult(ok=False, error="no_user", name=name, enhance=enhance)
        found = core.item_by_name(name)
        bag = await _count(openid, found.id, enhance) if found else 0
        slots = await _matching_slots(openid, name, enhance)
        available = bag + len(slots)
        take = available if quantity is None else quantity
        if take <= 0 or available < take:
            return RemoveItemResult(ok=False, error="not_enough", name=name, current=available, remaining=available,
                                    enhance=enhance)
        bag_take = min(take, bag)
        if bag_take:
            if enhance is not None:
                error, _ = await _take(openid, name, bag_take, enhance, temper=None)
            else:
                error, _ = await _take_any(openid, name, bag_take)
            if error:
                raise core.Rollback(RemoveItemResult(ok=False, error=error, name=name, current=available,
                                                 remaining=available, enhance=enhance))
        stripped: list[str] = []
        still = take - bag_take
        for e in slots:
            if still <= 0:
                break
            _clear(e)
            await e.save()
            stripped.append(e.slot)
            still -= 1
        remaining = (await _count(openid, found.id, enhance) if found else 0) + len(await _matching_slots(openid, name, enhance))
        return RemoveItemResult(ok=True, name=name, quantity=take, remaining=remaining, current=available,
                                enhance=enhance, from_equip=tuple(stripped))


# ---------------------------------------------------------------- 出售、分解、扩容


async def _picked(openid: str, index: int) -> InventoryItem | None:
    rows = await _rows(openid)
    return rows[index - 1] if 0 < index <= len(rows) else None


async def sell_inventory_at(openid: str, index: int, price_of: Callable[[str, int], int], quantity: int = 1) -> SellResult:
    if _bad_count(index):
        return SellResult(ok=False, error="no_item")
    if _bad_count(quantity):
        return SellResult(ok=False, error="bad_qty")
    async with core.tx():
        if not await Player.exists(openid=openid):
            return SellResult(ok=False, error="no_user")
        r = await _picked(openid, index)
        if r is None:
            return SellResult(ok=False, error="no_item")
        name = core.item_name(r.item_id)
        if r.quantity < quantity:
            return SellResult(ok=False, error="not_enough", name=name, enhance=r.enhance, quantity=r.quantity)
        unit = int(price_of(name, r.enhance))
        if unit < 0:
            return SellResult(ok=False, error="bad_qty", name=name, enhance=r.enhance)
        error, _ = await _take(openid, name, quantity, r.enhance, r.temper)
        if error:
            return SellResult(ok=False, error=error, name=name, enhance=r.enhance, quantity=r.quantity)
        payout = unit * quantity
        coins = await economy._add_coins(openid, payout)
        return SellResult(ok=True, name=name, enhance=r.enhance, quantity=quantity, payout=payout, coins=coins)


@core.rollback_result
async def sell_inventory_slots(openid: str, indices: list[int], price_of: Callable[[str, int], int]) -> BatchSellResult:
    unique: list[int] = []
    for index in indices:
        if _bad_count(index):
            return BatchSellResult(ok=False, error="no_item", index=index if isinstance(index, int) else 0)
        if index not in unique:
            unique.append(index)
    if not unique:
        return BatchSellResult(ok=False, error="no_item")
    async with core.tx():
        if not await Player.exists(openid=openid):
            return BatchSellResult(ok=False, error="no_user")
        rows = await _rows(openid)
        picked: list[tuple[str, int, int, int, int]] = []
        for index in unique:
            if index > len(rows):
                return BatchSellResult(ok=False, error="no_item", index=index)
            r = rows[index - 1]
            name = core.item_name(r.item_id)
            unit = int(price_of(name, r.enhance))
            if unit < 0:
                return BatchSellResult(ok=False, error="bad_qty", index=index)
            picked.append((name, r.enhance, r.temper, r.quantity, unit * r.quantity))
        lines: list[SellLine] = []
        for name, enhance, temper, quantity, payout in picked:
            error, _ = await _take(openid, name, quantity, enhance, temper)
            if error:
                raise core.Rollback(BatchSellResult(ok=False, error=error, index=unique[len(lines)]))
            lines.append(SellLine(name=name, enhance=enhance, quantity=quantity, payout=payout))
        total = sum(line.payout for line in lines)
        coins = await economy._add_coins(openid, total)
        return BatchSellResult(ok=True, items=tuple(lines), quantity=sum(line.quantity for line in lines),
                               payout=total, coins=coins)


@core.rollback_result
async def decompose_inventory_at(openid: str, index: int, quantity: int = 1) -> DecomposeResult:
    """分解：普通装备得副本保底，BOSS 装备得这个 BOSS 的精华（道具）；强化过的退还强化费用。"""
    if _bad_count(index):
        return DecomposeResult(ok=False, error="no_item")
    if _bad_count(quantity):
        return DecomposeResult(ok=False, error="bad_qty")
    async with core.tx():
        if not await Player.exists(openid=openid):
            return DecomposeResult(ok=False, error="no_user")
        r = await _picked(openid, index)
        if r is None:
            return DecomposeResult(ok=False, error="no_item")
        name, level = core.item_name(r.item_id), r.enhance
        if r.quantity < quantity:
            return DecomposeResult(ok=False, error="not_enough", name=name, quantity=r.quantity, enhance=level)
        found = info.decompose_info(name)
        if found is None:
            return DecomposeResult(ok=False, error="not_decomposable", name=name, enhance=level)
        error, _ = await _take(openid, name, quantity, level, r.temper)
        if error:
            return DecomposeResult(ok=False, error=error, name=name, quantity=r.quantity, enhance=level)
        refund = info.enhance_refund(level) * quantity
        coins = await economy._add_coins(openid, refund) if refund > 0 else int((await core.wallet(openid)).coins)
        essence = ""
        pity_gain = 0
        pity_total = await core.read_pity(openid)
        if found.kind == "boss":
            essence_prop = core.prop_by_name(found.essence)
            if essence_prop is None:
                raise core.Rollback(DecomposeResult(ok=False, error="no_essence", name=name, enhance=level))
            from .props import _add_warehouse
            await _add_warehouse(openid, essence_prop.id, quantity)
            essence = found.essence
        else:
            pity_gain = found.pity * quantity
            pity_total = await core.write_pity(openid, pity_total + pity_gain)
        return DecomposeResult(ok=True, name=name, quantity=quantity, enhance=level, essence=essence, pity=pity_gain,
                               pity_total=pity_total, refund=refund, coins=coins)


async def expand_bag_at(openid: str, index: int) -> BagExpandResult:
    """用一颗隐秘宝石扩容背包 2 格（每种宝石只能用一次），费用 10000 × 第几次 × 副本编号。"""
    if _bad_count(index):
        return BagExpandResult(ok=False, error="no_item")
    async with core.tx():
        if not await Player.exists(openid=openid):
            return BagExpandResult(ok=False, error="no_user")
        r = await _picked(openid, index)
        if r is None:
            return BagExpandResult(ok=False, error="no_item")
        name, level = core.item_name(r.item_id), r.enhance
        dungeon_id = info.hidden_gem_dungeon(name)
        if dungeon_id <= 0:
            return BagExpandResult(ok=False, error="not_hidden", name=name, enhance=level)
        if await BagExpand.exists(player_id=openid, gem_name=name):
            return BagExpandResult(ok=False, error="already", name=name, enhance=level)
        cost = tuning.value('bag_expand_coin') * (await economy.bag_expand_count(openid) + 1) * dungeon_id
        w = await core.wallet(openid)
        if int(w.coins) < cost:
            return BagExpandResult(ok=False, error="no_coins", name=name, enhance=level, cost=cost, coins=int(w.coins))
        error, _ = await _take(openid, name, 1, level, r.temper)
        if error:
            return BagExpandResult(ok=False, error=error, name=name, enhance=level, cost=cost, coins=int(w.coins))
        coins = await economy._add_coins(openid, -cost)
        await BagExpand.create(player_id=openid, gem_name=name)
    return BagExpandResult(ok=True, name=name, enhance=level, cost=cost, coins=coins,
                           kinds=await economy.max_item_kinds(openid))


# ---------------------------------------------------------------- 装备合成


@core.rollback_result
async def craft_items(openid: str, inputs: list[tuple[str, int]], output_name: str, output_qty: int,
                      enhance_refund: Callable[[int], int] | None = None) -> CraftResult:
    """用材料合成装备：材料强化高的先用；成品继承材料里最高的强化等级（宝石不继承），其余强化退还费用。"""
    output_name = output_name.strip()
    if not output_name:
        return CraftResult(ok=False, error="bad_name")
    if _bad_count(output_qty):
        return CraftResult(ok=False, error="bad_qty", output=output_name)
    cleaned: list[tuple[str, int]] = []
    for name, quantity in inputs:
        name = name.strip()
        if not name or _bad_count(quantity):
            return CraftResult(ok=False, error="bad_qty", output=output_name, missing=name)
        cleaned.append((name, quantity))
    if not cleaned:
        return CraftResult(ok=False, error="bad_qty", output=output_name)
    async with core.tx():
        if not await Player.exists(openid=openid):
            return CraftResult(ok=False, error="no_user", output=output_name)
        for name, quantity in cleaned:
            held = await inventory_count(openid, name)
            if held < quantity:
                return CraftResult(ok=False, error="not_enough", output=output_name, missing=name, current=held,
                                   quantity=quantity)
        consumed: list[int] = []
        for name, quantity in cleaned:
            error, levels = await _take_any(openid, name, quantity, highest_first=True)
            if error:
                raise core.Rollback(CraftResult(ok=False, error=error, output=output_name, missing=name, quantity=quantity))
            consumed.extend(levels)
        gem = core.item_slot(output_name) == "gem"
        inherited = 0 if gem else max(consumed, default=0)
        refund_levels = list(consumed)
        if not gem and inherited in refund_levels:
            refund_levels.remove(inherited)
        refund = sum(max(0, int(enhance_refund(lv))) for lv in refund_levels) if enhance_refund else 0
        added = await _add(openid, output_name, output_qty, inherited)
        if not added.ok:
            raise core.Rollback(CraftResult(ok=False, error=added.error, output=output_name, quantity=output_qty,
                                        current=added.current, enhance=inherited))
        coins = await economy._add_coins(openid, refund) if refund > 0 else int((await core.wallet(openid)).coins)
        return CraftResult(ok=True, output=output_name, quantity=output_qty, current=added.quantity,
                           enhance=inherited, refund=refund, coins=coins)


# ---------------------------------------------------------------- 指令里的计算（原来写在背包插件里）


def unit_price(name: str, level: int) -> int:
    """出售单价：基础价格 + 强化返还。"""
    found = core.item_by_name(name)
    return (found.price if found else 0) + info.enhance_refund(level)


async def sell(openid: str, index: int, quantity: int = 1) -> SellResult:
    return await sell_inventory_at(openid, index, unit_price, quantity)


async def sell_many(openid: str, indices: list[int]) -> BatchSellResult:
    return await sell_inventory_slots(openid, indices, unit_price)


async def craft_recipe(openid: str, recipe_id: int) -> CraftResult:
    """"合成 <编号>"：按装备配方合成，材料多出来的强化等级退还费用。"""
    recipe = core.rules().recipes.get(recipe_id)
    if recipe is None:
        return CraftResult(ok=False, error="no_recipe")
    return await craft_items(openid, [(i.name, i.quantity) for i in recipe.inputs], recipe.output, recipe.quantity,
                             info.enhance_refund)
