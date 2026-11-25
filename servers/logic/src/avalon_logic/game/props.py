"""道具仓库：发放、购买、使用、合成、兑换码、世界币商城、符咒（对应旧版 db.py 的道具部分）。

道具的定义（名称、效果、数值、说明、所属副本）来自规则库；仓库里按格子编号显示，用完的格子后面的往前补。
"""

from __future__ import annotations

import hashlib
import random
import secrets
import string

from avalon_contracts.rules.prop import PropDef

from ..store.models.game import (
    EasterRedeem,
    LastChallenge,
    Player,
    PropBuff,
    RedeemCode,
    WarehouseItem,
)
from . import bag, checkin, core, economy, info, tuning
from .constants import (
    DUNGEON_CHARM_EFFECTS,
    ENHANCE_CHARM_EFFECTS,
    LURE_KINDS,
)
from .results import BuyResult, GiftBoxInfo, PropResult, WarehouseRow, WorldShopResult

FRAGMENT_NAME = "礼盒碎片"
GIFT_BOX_NAME = "小礼盒"
FRAGMENT_COST = 9
_EQUIP_KIND_WEIGHTS = (("normal", 60), ("elite", 30), ("boss", 10))

_CODE_UPPER = string.ascii_uppercase
_CODE_LOWER = string.ascii_lowercase
_CODE_DIGIT = string.digits
_CODE_SPECIAL = "!@#$%&*+-_=?"
_CODE_ALPHABET = _CODE_UPPER + _CODE_LOWER + _CODE_DIGIT + _CODE_SPECIAL


def _bad(q: object) -> bool:
    return not isinstance(q, int) or isinstance(q, bool) or q <= 0


# ---------------------------------------------------------------- 仓库格子


async def _quantity(openid: str, prop_id: int) -> int:
    row = await WarehouseItem.get_or_none(player_id=openid, prop_id=prop_id)
    return row.quantity if row else 0


async def _add_warehouse(openid: str, prop_id: int, quantity: int) -> int:
    row = await WarehouseItem.get_or_none(player_id=openid, prop_id=prop_id)
    if row is None:
        slots = await WarehouseItem.filter(player_id=openid).values_list("slot", flat=True)
        await WarehouseItem.create(player_id=openid, prop_id=prop_id, quantity=quantity, slot=max(slots, default=0) + 1)
        return quantity
    row.quantity += quantity
    await row.save(update_fields=["quantity"])
    return row.quantity


async def _renumber(openid: str) -> None:
    rows = await WarehouseItem.filter(player_id=openid).order_by("slot", "prop_id")
    for index, row in enumerate(rows, start=1):
        if row.slot != index:
            row.slot = index
            await row.save(update_fields=["slot"])


async def _take_quantity(openid: str, prop_id: int, quantity: int) -> None:
    row = await WarehouseItem.get_or_none(player_id=openid, prop_id=prop_id)
    if row is None:
        return
    left = row.quantity - quantity
    if left <= 0:
        await row.delete()
        await _renumber(openid)
    else:
        row.quantity = left
        await row.save(update_fields=["quantity"])


async def _prop_by_key(openid: str, key: str) -> PropDef | None:
    """按仓库格子编号或道具名找道具。"""
    text = key.strip()
    if text.isdigit():
        row = await WarehouseItem.get_or_none(player_id=openid, slot=int(text))
        return core.prop(row.prop_id) if row else None
    return core.prop_by_name(text)


async def list_warehouse(openid: str) -> list[WarehouseRow]:
    rows = await WarehouseItem.filter(player_id=openid, quantity__gt=0).order_by("slot")
    return [WarehouseRow(slot=r.slot, name=core.prop(r.prop_id).name if core.prop(r.prop_id) else "", quantity=r.quantity)
            for r in rows]


async def warehouse_quantity(openid: str, name: str) -> int:
    found = core.prop_by_name(name)
    return 0 if found is None else await _quantity(openid, found.id)


async def grant_prop(openid: str, name: str, quantity: int) -> PropResult:
    if _bad(quantity):
        return PropResult(ok=False, error="bad_qty")
    async with core.tx():
        if not await Player.exists(openid=openid):
            return PropResult(ok=False, error="no_user")
        found = core.prop_by_name(name)
        if found is None:
            return PropResult(ok=False, error="unknown")
        return PropResult(ok=True, name=found.name, quantity=await _add_warehouse(openid, found.id, quantity))


async def remove_prop(openid: str, name: str, amount: int | None):
    """扣除仓库道具，最少扣到 0；amount 为 None 时清空。"""
    from .results import AdjustResult

    if amount is not None and _bad(amount):
        return AdjustResult(ok=False, error="bad_qty")
    async with core.tx():
        if not await Player.exists(openid=openid):
            return AdjustResult(ok=False, error="no_user")
        found = core.prop_by_name(name)
        if found is None:
            return AdjustResult(ok=False, error="unknown")
        held = await _quantity(openid, found.id)
        take = held if amount is None else min(held, amount)
        if take > 0:
            await _take_quantity(openid, found.id, take)
    return AdjustResult(ok=True, removed=take, current=held - take)


def find_gift_box(dungeon_name: str) -> GiftBoxInfo | None:
    """按副本名找随机礼盒道具（效果 equip、所属副本是这个副本）。"""
    found = next((p for p in sorted(core.rules().props.values(), key=lambda p: p.id)
                  if p.effect == "equip" and p.dungeon == dungeon_name), None)
    return GiftBoxInfo(name=found.name, value=found.value) if found else None


async def buy_prop(openid: str, name: str, cost: int, quantity: int = 1) -> BuyResult:
    """花代币购买道具入仓库。"""
    if _bad(cost) or _bad(quantity):
        return BuyResult(ok=False, error="bad_qty")
    total_cost = cost * quantity
    async with core.tx():
        if not await Player.exists(openid=openid):
            return BuyResult(ok=False, error="no_user", name=name)
        found = core.prop_by_name(name)
        if found is None:
            return BuyResult(ok=False, error="unknown", name=name)
        balance = int((await core.wallet(openid)).coins)
        if balance < total_cost:
            return BuyResult(ok=False, error="no_coins", name=name, cost=total_cost, coins=balance)
        coins = await economy._add_coins(openid, -total_cost)
        total = await _add_warehouse(openid, found.id, quantity)
    return BuyResult(ok=True, name=found.name, cost=total_cost, coins=coins, quantity=total)


async def buy_world_prop(openid: str, index: int, quantity: int = 1) -> WorldShopResult:
    """世界币商城：1=强化道具随机礼盒、2=副本道具随机礼盒，单价 10 世界币。"""
    if index not in (1, 2):
        return WorldShopResult(ok=False, error="bad_index")
    if _bad(quantity):
        return WorldShopResult(ok=False, error="bad_qty")
    name = tuning.value('world_shop_items')[index - 1]
    async with core.tx():
        if not await Player.exists(openid=openid):
            return WorldShopResult(ok=False, error="no_user")
        box = core.prop_by_name(name)
        if box is None:
            return WorldShopResult(ok=False, error="unknown", name=name)
        w = await core.wallet(openid)
        balance = int(w.world_coins)
        cost = tuning.value('world_shop_price') * quantity
        if balance < cost:
            return WorldShopResult(ok=False, error="no_coins", name=name, quantity=quantity, cost=cost,
                                   world_coins=balance)
        await economy._add_world_coins(openid, -cost)
        total = await _add_warehouse(openid, box.id, quantity)
        return WorldShopResult(ok=True, name=name, quantity=total, cost=cost, world_coins=balance - cost)


# ---------------------------------------------------------------- 符咒（下一次强化 / 副本挑战时消耗）


async def _set_buff(openid: str, effect: str, amount: int, note: str = "") -> None:
    """同类符咒（强化类 / 副本类）只生效一种：新用的覆盖之前的。"""
    category = ENHANCE_CHARM_EFFECTS if effect in ENHANCE_CHARM_EFFECTS else DUNGEON_CHARM_EFFECTS
    await PropBuff.filter(player_id=openid, effect__in=list(category)).delete()
    await PropBuff.create(player_id=openid, effect=effect, amount=amount, note=note)


async def _read_buffs(openid: str, effects: tuple[str, ...]) -> dict[str, tuple[int, str]]:
    if not effects:
        return {}
    rows = await PropBuff.filter(player_id=openid, effect__in=list(effects))
    return {r.effect: (r.amount, r.note) for r in rows}


async def peek_prop_buffs(openid: str, effects: tuple[str, ...]) -> dict[str, tuple[int, str]]:
    return await _read_buffs(openid, effects)


async def _take_buffs(openid: str, effects: tuple[str, ...]) -> dict[str, tuple[int, str]]:
    buffs = await _read_buffs(openid, effects)
    if buffs:
        await PropBuff.filter(player_id=openid, effect__in=list(buffs)).delete()
    return buffs


async def take_prop_buffs(openid: str, effects: tuple[str, ...]) -> dict[str, tuple[int, str]]:
    """读取并清除待生效符咒（副本/强化开始时调用）。"""
    async with core.tx():
        return await _take_buffs(openid, effects)


async def clear_prop_buffs(openid: str, effects: tuple[str, ...]) -> None:
    if not effects:
        return
    async with core.tx():
        await PropBuff.filter(player_id=openid, effect__in=list(effects)).delete()


async def set_last_challenge(openid: str, dungeon_id: int, monster_id: str) -> None:
    """记录最近一次副本主战遇到的怪（锁影符重复挑战用）。"""
    async with core.tx():
        row = await LastChallenge.get_or_none(player_id=openid)
        if row is None:
            await LastChallenge.create(player_id=openid, dungeon_id=dungeon_id, monster_id=monster_id)
        else:
            row.dungeon_id, row.monster_id = dungeon_id, monster_id
            await row.save()


async def get_last_challenge(openid: str) -> tuple[int, str] | None:
    row = await LastChallenge.get_or_none(player_id=openid)
    return (row.dungeon_id, row.monster_id) if row else None


# ---------------------------------------------------------------- 使用


def _roll_equip_box(pools: dict[str, list[str]]) -> str | None:
    weighted = [(weight, names) for kind, weight in tuning.value('equip_kind_weights') if (names := pools.get(kind, []))]
    if not weighted:
        return None
    total = sum(w for w, _ in weighted)
    roll = random.randrange(total)
    acc = 0
    for weight, names in weighted:
        acc += weight
        if roll < acc:
            return random.choice(names)
    return random.choice(weighted[-1][1])


def _opened(counts: dict[str, int]) -> str:
    return "、".join(f"{item}x{count}" for item, count in counts.items())


async def prop_effect(openid: str, key: str) -> str:
    """仓库道具的效果代号（使用指令按效果解析参数用）。"""
    found = await _prop_by_key(openid, key)
    return found.effect if found else ""


@core.rollback_result
async def use_prop(openid: str, key: str, quantity: int = 1, choice: str = "") -> PropResult:
    if _bad(quantity):
        return PropResult(ok=False, error="bad_qty")
    async with core.tx():
        player = await core.get_player(openid)
        if player is None:
            return PropResult(ok=False, error="no_user")
        found = await _prop_by_key(openid, key)
        if found is None:
            return PropResult(ok=False, error="unknown")
        name, effect, blurb = found.name, found.effect, found.blurb

        def fail(error: str, **kw) -> core.Rollback:
            return core.Rollback(PropResult(ok=False, error=error, name=name, blurb=blurb, **kw))

        if effect in ("fragment", "material"):
            return PropResult(ok=False, error="material", name=name, blurb=blurb)
        if effect == "boss_choice" and not choice.strip():
            return PropResult(ok=False, error="need_name", name=name, blurb=blurb)
        held = await _quantity(openid, found.id)
        if held <= 0:
            return PropResult(ok=False, error="empty", name=name, blurb=blurb)
        if held < quantity:
            return PropResult(ok=False, error="short", name=name, quantity=held, blurb=blurb)
        await _take_quantity(openid, found.id, quantity)

        def ok(detail: str, qty: int = quantity) -> PropResult:
            return PropResult(ok=True, name=name, quantity=qty, detail=detail, blurb=blurb)

        if effect == "boss_choice":
            picked = choice.strip()
            if picked not in info.boss_equipment(found.dungeon or ""):
                raise fail("bad_choice")
            added = await bag._add(openid, picked, quantity)
            if not added.ok:
                raise fail(added.error or "", detail=picked)
            return ok(f"获得 {picked} x{quantity}")
        if effect == "box":
            choices = sorted((p for p in core.rules().props.values() if p.effect in ("stamina", "exp", "coins")),
                             key=lambda p: p.id)
            if not choices:
                raise fail("empty")
            counts: dict[str, int] = {}
            for _ in range(quantity):
                gained = random.choice(choices)
                counts[gained.name] = counts.get(gained.name, 0) + 1
                await _add_warehouse(openid, gained.id, 1)
            return ok(f"开出 {_opened(counts)}")
        if effect == "equip":
            pools = info.equipment_by_kind(found.dungeon or "")
            if not any(pools.values()):
                raise fail("no_equip")
            counts = {}
            for _ in range(quantity):
                picked = _roll_equip_box(pools)
                if not picked:
                    raise fail("no_equip")
                added = await bag._add(openid, picked, 1)
                if not added.ok:
                    raise fail(added.error or "")
                counts[picked] = counts.get(picked, 0) + 1
            return ok(f"开出 {_opened(counts)}")
        if effect == "exp_pct":
            # 世界经验药：按当前升级所需经验的百分比给经验（可以升级）
            gain = economy.exp_to_next_for(player.level) * found.amount * quantity // 100
            level, _, _, gained = await economy._apply_exp(player, gain)
            detail = f"获得 {gain} 经验"
            if gained:
                detail += f"，升级 +{gained}，当前 {level} 级"
            return ok(detail)
        if effect == "makeup_checkin":
            # 补签符：每张补签一天；缺的天数比张数少时只用掉实际补签的天数
            result = await checkin._makeup(openid, quantity)
            if not result.ok:
                raise fail(result.error or "")
            refund = quantity - result.days
            if refund > 0:
                await _add_warehouse(openid, found.id, refund)
            detail = f"补签 {result.days} 天，获得 {result.gained} 体力"
            if result.restored:
                detail += "，已恢复连续签到"
            elif result.owed > 0:
                detail += f"，还缺 {result.owed} 天"
            return ok(detail, result.days)
        if effect in ("box_strengthen", "box_dungeon"):
            pool = tuning.value('enhance_box_pool') if effect == "box_strengthen" else tuning.value('dungeon_box_pool')
            picks = [(p, w) for pool_name, w in pool if (p := core.prop_by_name(pool_name)) is not None]
            if not picks:
                raise fail("empty")
            counts = {}
            for gained in random.choices([p for p, _ in picks], weights=[w for _, w in picks], k=quantity):
                counts[gained.name] = counts.get(gained.name, 0) + 1
                await _add_warehouse(openid, gained.id, 1)
            return ok(f"开出 {_opened(counts)}")
        if effect in ENHANCE_CHARM_EFFECTS:
            amount = found.amount * quantity
            await _set_buff(openid, effect, amount)
            return ok({"enhance_bless": f"下次强化成功率+{amount}%",
                       "enhance_protect": f"下次强化失败返还{amount}%代币",
                       "enhance_miracle": f"下次强化{found.amount}%概率额外升1级"}[effect])
        if effect == "dungeon_lure":
            kind = LURE_KINDS.get(choice.strip())
            if kind is None:
                raise fail("need_kind")
            await _set_buff(openid, effect, 1, kind)
            return ok(f"下次副本挑战强制遇到{choice.strip()}")
        if effect == "dungeon_cross":
            # 跨界符：从已解锁副本里任选一个怪物挑战；挑战由调用方在成功后立即发起
            if not choice.strip():
                raise fail("need_monster")
            m = info.find_monster(choice.strip())
            if m is None:
                raise fail("bad_monster")
            if info.cross_dungeon_for(m.id, player.level) is None:
                raise fail("locked")
            return ok(f"已选择怪物 {m.name}")
        if effect in DUNGEON_CHARM_EFFECTS:
            await _set_buff(openid, effect, found.amount)
            return ok("已生效，将在下次副本挑战时消耗")
        amount = found.amount * quantity
        if effect == "stamina":
            current = min(tuning.value('stamina_cap'), player.stamina + amount)
            added_stamina = current - player.stamina
            if added_stamina <= 0:
                raise fail("stamina_full")     # 体力已满：不吃药，道具不扣
            player.stamina = current
            await player.save(update_fields=["stamina"])
            return ok(f"恢复体力 {added_stamina}，当前 {current}")
        if effect == "coins":
            current = await economy._add_coins(openid, amount)
            return ok(f"获得代币 {amount}，当前 {current}")
        if effect == "exp":
            level, current_exp, need, gained = await economy._apply_exp(player, amount)
            extra = f"，升级 {gained}" if gained else ""
            return ok(f"获得经验 {amount}，等级 {level}（{current_exp}/{need}）{extra}")
        raise fail("unknown")


# ---------------------------------------------------------------- 合成


def list_prop_recipes() -> list[dict]:
    """保留旧版字段，并返回每份成品 quantity；请求数量表示合成份数。"""
    recipes = [{"id": r.id, "name": r.output, "quantity": r.quantity, "inputs": [{"name": i.name, "quantity": i.quantity} for i in r.inputs]}
               for r in sorted(core.rules().prop_recipes.values(), key=lambda r: r.id)]
    if not any(r["name"] == GIFT_BOX_NAME for r in recipes):
        recipes.append({"name": GIFT_BOX_NAME, "quantity": 1, "inputs": [{"name": FRAGMENT_NAME, "quantity": tuning.value('fragment_cost')}]})
    return recipes


def _recipe_for(output_name: str) -> dict | None:
    return next((r for r in list_prop_recipes() if r["name"] == output_name), None)


async def craft_prop(openid: str, output_name: str, quantity: int = 1) -> PropResult:
    """按配方合成道具，可以一次合成多份。"""
    recipe = _recipe_for(output_name.strip())
    if recipe is None:
        return PropResult(ok=False, error="unknown", name=output_name)
    if _bad(quantity):
        return PropResult(ok=False, error="bad_qty", name=output_name)
    async with core.tx():
        if not await Player.exists(openid=openid):
            return PropResult(ok=False, error="no_user")
        output = core.prop_by_name(recipe["name"])
        if output is None:
            return PropResult(ok=False, error="unknown", name=recipe["name"])
        needed: list[tuple[int, int]] = []
        for entry in recipe["inputs"]:
            material = core.prop_by_name(entry["name"])
            if material is None:
                return PropResult(ok=False, error="unknown", name=entry["name"])
            want = int(entry["quantity"]) * quantity
            held = await _quantity(openid, material.id)
            if held < want:
                return PropResult(ok=False, error="short", name=entry["name"], quantity=held, detail=str(want))
            needed.append((material.id, want))
        for prop_id, want in needed:
            await _take_quantity(openid, prop_id, want)
        total = await _add_warehouse(openid, output.id, quantity * int(recipe.get("quantity", 1)))
    return PropResult(ok=True, name=output.name, quantity=total)


# ---------------------------------------------------------------- 兑换码


def _redeem_code_text(digest: bytes) -> str:
    chars = [_CODE_ALPHABET[digest[i] % len(_CODE_ALPHABET)] for i in range(15)]
    for index, pool in enumerate((_CODE_UPPER, _CODE_LOWER, _CODE_DIGIT, _CODE_SPECIAL)):
        chars[index] = pool[digest[index] % len(pool)]
    for index in range(15):
        swap = digest[index % len(digest)] % 15
        chars[index], chars[swap] = chars[swap], chars[index]
    return "".join(chars)


async def create_redeem_code(name: str, quantity: int, blocked: set[str]) -> PropResult:
    if _bad(quantity):
        return PropResult(ok=False, error="bad_qty")
    async with core.tx():
        found = core.prop_by_name(name)
        if found is None:
            return PropResult(ok=False, error="unknown")
        banned = {item.strip() for item in blocked if item.strip()}
        code = ""
        for _ in range(32):
            candidate = _redeem_code_text(hashlib.md5(secrets.token_bytes(32)).digest())
            if candidate in banned or await RedeemCode.exists(code=candidate):
                continue
            code = candidate
            break
        if not code:
            return PropResult(ok=False, error="busy", name=found.name)
        await RedeemCode.create(code=code, prop_id=found.id, quantity=quantity, used=False)
    return PropResult(ok=True, name=found.name, quantity=quantity, detail=code)


async def redeem_code(openid: str, code: str, easter_codes: set[str]) -> PropResult:
    text = code.strip()
    if not text:
        return PropResult(ok=False, error="unknown")
    async with core.tx():
        if not await Player.exists(openid=openid):
            return PropResult(ok=False, error="no_user")
        if text in easter_codes:
            if await EasterRedeem.exists(code=text, player_id=openid):
                return PropResult(ok=False, error="used", name="体力药（中）")
            found = core.prop_by_name("体力药（中）")
            if found is None:
                return PropResult(ok=False, error="unknown")
            await EasterRedeem.create(code=text, player_id=openid)
            return PropResult(ok=True, name=found.name, quantity=await _add_warehouse(openid, found.id, 1), detail="1")
        row = await RedeemCode.get_or_none(code=text)
        found = core.prop(row.prop_id) if row else None
        if row is None or found is None:
            return PropResult(ok=False, error="unknown")
        if row.used:
            return PropResult(ok=False, error="used", name=found.name)
        total = await _add_warehouse(openid, row.prop_id, row.quantity)
        row.used = True
        await row.save(update_fields=["used"])
    return PropResult(ok=True, name=found.name, quantity=total, detail=str(row.quantity))


async def buy_gift_box(openid: str, dungeon_id: int, quantity: int = 1) -> BuyResult:
    """"商城 土罐 <副本编号>"：买这个副本的随机礼盒（需要 副本号×5+2 级）。
    错误：no_dungeon、level（等级不够，name 里是需要的等级）、no_box、no_price。"""
    d = info.dungeon(dungeon_id)
    if d is None:
        return BuyResult(ok=False, error="no_dungeon")
    player = await core.get_player(openid)
    if player is None:
        return BuyResult(ok=False, error="no_user")
    if player.level < d.id * 5 + 2:
        return BuyResult(ok=False, error="level", name=str(d.id * 5 + 2))
    box = find_gift_box(d.name)
    if box is None:
        return BuyResult(ok=False, error="no_box")
    if box.value <= 0:
        return BuyResult(ok=False, error="no_price", name=box.name)
    return await buy_prop(openid, box.name, box.value, quantity)
