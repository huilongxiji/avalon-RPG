"""市场：上架、购买、下架（对应旧版 db.py 的市场部分）。

上架时按挂单总价扣 5% 手续费（下架不退）；每人每个自然周最多上架 30 次；定制宝石不能上架；
单价不能低于（50% 基础价格 + 50% 强化开销）；成交单价超过 10 倍基础价格 + 强化总开销时，卖家所得再扣 75%。
新版把淬炼度也记在挂单上，成交和下架时随装备一起转移（旧版会丢掉淬炼度）。
"""

from __future__ import annotations

from collections.abc import Callable

from ..store.models.game import MarketListing, MarketWeekly, Player, SponsorGem
from . import bag, core, economy, info, tuning
from .results import MarketListingView, MarketOpResult


def market_fee(gross: int) -> int:
    return min(gross, int(tuning.formula('market_fee', gross=gross, percent=tuning.value('market_fee_percent'))))


def _week_key() -> str:
    iso = core.today().isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def price_cap(name: str, enhance: int) -> int | None:
    found = core.item_by_name(name)
    if found is None:
        return None
    return max(0, found.price) * tuning.value('market_price_cap_ratio') + info.enhance_total_cost(max(0, int(enhance)))


def min_price(name: str, enhance: int) -> int:
    found = core.item_by_name(name)
    return info.market_min_price(found.price if found else 0, enhance)


async def market_week_used(openid: str) -> int:
    row = await MarketWeekly.get_or_none(player_id=openid, week=_week_key())
    return row.used if row else 0


async def list_market() -> list[MarketListingView]:
    rows = await MarketListing.filter(quantity__gt=0).order_by("id")
    return [MarketListingView(id=r.id, seller_openid=r.seller_id, name=core.item_name(r.item_id),  # type: ignore[attr-defined]
                              quantity=r.quantity, unit_price=int(r.unit_price), enhance=r.enhance) for r in rows]


def _bad(v: object) -> bool:
    return not isinstance(v, int) or isinstance(v, bool) or v <= 0


@core.rollback_result
async def list_on_market(seller_openid: str, index: int, quantity: int, unit_price: int,
                         min_price_of: Callable[[str, int], int] = min_price) -> MarketOpResult:
    if _bad(index):
        return MarketOpResult(ok=False, error="no_item")
    if _bad(quantity):
        return MarketOpResult(ok=False, error="bad_qty")
    if _bad(unit_price):
        return MarketOpResult(ok=False, error="bad_price")
    async with core.tx():
        if not await Player.exists(openid=seller_openid):
            return MarketOpResult(ok=False, error="no_user")
        r = await bag._picked(seller_openid, index)
        if r is None:
            return MarketOpResult(ok=False, error="no_item")
        name, enhance, temper = core.item_name(r.item_id), r.enhance, r.temper
        if r.quantity < quantity:
            return MarketOpResult(ok=False, error="not_enough", name=name, quantity=r.quantity, enhance=enhance)
        if await SponsorGem.exists(name=name):
            return MarketOpResult(ok=False, error="personal", name=name, enhance=enhance)
        floor = int(min_price_of(name, enhance))
        if floor < 0:
            return MarketOpResult(ok=False, error="bad_price", name=name, enhance=enhance)
        if unit_price < floor:
            return MarketOpResult(ok=False, error="low_price", name=name, quantity=quantity, unit_price=floor,
                                  enhance=enhance)
        week = await MarketWeekly.get_or_none(player_id=seller_openid, week=_week_key())
        if (week.used if week else 0) >= tuning.value('market_list_limit'):
            return MarketOpResult(ok=False, error="week_full", name=name, quantity=quantity, unit_price=unit_price,
                                  enhance=enhance)
        fee = market_fee(unit_price * quantity)
        balance = int((await core.wallet(seller_openid)).coins)
        if balance < fee:
            return MarketOpResult(ok=False, error="no_coins", name=name, quantity=quantity, unit_price=unit_price,
                                  enhance=enhance, paid=fee)
        coins = await economy._add_coins(seller_openid, -fee)
        if week is None:
            await MarketWeekly.create(player_id=seller_openid, week=_week_key(), used=1)
        else:
            week.used += 1
            await week.save(update_fields=["used"])
        error, _ = await bag._take(seller_openid, name, quantity, enhance, temper)
        if error:
            raise core.Rollback(MarketOpResult(ok=False, error=error, name=name, quantity=r.quantity, enhance=enhance))
        listing = await MarketListing.create(seller_id=seller_openid, item_id=r.item_id, quantity=quantity,
                                             unit_price=unit_price, enhance=enhance, temper=temper)
        return MarketOpResult(ok=True, listing_id=listing.id, name=name, quantity=quantity, unit_price=unit_price,
                              seller_openid=seller_openid, enhance=enhance, fee=fee, coins=coins)



@core.rollback_result
async def buy_listing(buyer_openid: str, listing_id: int, quantity: int | None) -> MarketOpResult:
    if _bad(listing_id):
        return MarketOpResult(ok=False, error="no_listing")
    async with core.tx():
        if not await Player.exists(openid=buyer_openid):
            return MarketOpResult(ok=False, error="no_user")
        row = await MarketListing.get_or_none(id=listing_id)
        if row is None or row.quantity <= 0:
            return MarketOpResult(ok=False, error="no_listing")
        seller = row.seller_id  # type: ignore[attr-defined]
        name, available, unit_price, enhance = core.item_name(row.item_id), row.quantity, int(row.unit_price), row.enhance
        if seller == buyer_openid:
            return MarketOpResult(ok=False, error="own_listing", listing_id=listing_id, name=name)
        buy_qty = available if quantity is None else quantity
        if _bad(buy_qty):
            return MarketOpResult(ok=False, error="bad_qty", name=name)
        if buy_qty > available:
            return MarketOpResult(ok=False, error="not_enough", listing_id=listing_id, name=name, quantity=available)
        paid = buy_qty * unit_price
        cap = price_cap(name, enhance)
        fee = min(paid, int(tuning.formula('market_fee', gross=paid, percent=tuning.value('market_extra_fee_percent')))) if cap is not None and unit_price > cap else 0
        if int((await core.wallet(buyer_openid)).coins) < paid:
            return MarketOpResult(ok=False, error="no_coins", name=name, quantity=buy_qty, paid=paid)
        added = await bag._add(buyer_openid, name, buy_qty, enhance, row.temper)
        if not added.ok:
            raise core.Rollback(MarketOpResult(ok=False, error=added.error, name=name, quantity=buy_qty,
                                               current=added.current, enhance=enhance))
        await economy._add_coins(buyer_openid, -paid)
        await economy._add_coins(seller, paid - fee)
        if available == buy_qty:
            await row.delete()
        else:
            row.quantity = available - buy_qty
            await row.save(update_fields=["quantity"])
        return MarketOpResult(ok=True, listing_id=listing_id, name=name, quantity=buy_qty, unit_price=unit_price,
                              paid=paid, fee=fee, seller_gain=paid - fee, seller_openid=seller, enhance=enhance)


async def cancel_listing(seller_openid: str, listing_id: int) -> MarketOpResult:
    if _bad(listing_id):
        return MarketOpResult(ok=False, error="no_listing")
    async with core.tx():
        row = await MarketListing.get_or_none(id=listing_id)
        if row is None or row.quantity <= 0:
            return MarketOpResult(ok=False, error="no_listing")
        if row.seller_id != seller_openid:  # type: ignore[attr-defined]
            return MarketOpResult(ok=False, error="not_seller", listing_id=listing_id)
        name = core.item_name(row.item_id)
        added = await bag._add(seller_openid, name, row.quantity, row.enhance, row.temper)
        if not added.ok:
            return MarketOpResult(ok=False, error=added.error, listing_id=listing_id, name=name, quantity=row.quantity,
                                  current=added.current)
        await row.delete()
        return MarketOpResult(ok=True, listing_id=listing_id, name=name, quantity=row.quantity,
                              unit_price=int(row.unit_price), seller_openid=seller_openid, enhance=row.enhance)
