"""各种操作的返回结果（字段和旧版 db.py 一样，方便 bot 前端照旧显示）。

ok 为 False 时 error 是错误码（见 avalon_contracts.errors），例如 no_user、bad_qty、no_coins。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Panel:
    openid: str
    level: int
    exp: int
    exp_to_next: int
    hp: int
    atk: int
    defense: int
    agi: int
    mp: int
    penetration: int
    stamina: int
    special_stamina: int
    weapon: str
    armor: str
    bracelet: str
    necklace: str
    gem: str
    weapon_enhance: int
    armor_enhance: int
    bracelet_enhance: int
    necklace_enhance: int
    gem_enhance: int
    weapon_temper: int
    armor_temper: int
    bracelet_temper: int
    necklace_temper: int
    gem_temper: int
    coins: int
    world_coins: int


@dataclass(frozen=True)
class CheckinResult:
    created: bool
    already_today: bool
    rank: int
    count: int
    stamina: int
    gained: int = 0
    streak: int = 0
    owed: int = 0
    pity_gained: int = 0
    pity: int = 0


@dataclass(frozen=True)
class MakeupResult:
    ok: bool
    error: str | None = None
    days: int = 0
    gained: int = 0
    count: int = 0
    streak: int = 0
    owed: int = 0
    stamina: int = 0
    restored: bool = False


@dataclass(frozen=True)
class EquipResult:
    ok: bool
    error: str | None = None
    slot: str = ""
    name: str = ""
    replaced: str = ""
    enhance: int = 0
    replaced_enhance: int = 0
    current: int = 0


@dataclass(frozen=True)
class AddItemResult:
    ok: bool
    error: str | None = None
    name: str = ""
    quantity: int = 0
    current: int = 0


@dataclass(frozen=True)
class AdjustResult:
    ok: bool
    error: str | None = None
    removed: int = 0
    current: int = 0


@dataclass(frozen=True)
class RemoveItemResult:
    ok: bool
    error: str | None = None
    name: str = ""
    quantity: int = 0
    remaining: int = 0
    current: int = 0
    enhance: int | None = None
    from_equip: tuple[str, ...] = ()


@dataclass(frozen=True)
class MarketListingView:
    id: int
    seller_openid: str
    name: str
    quantity: int
    unit_price: int
    enhance: int = 0


@dataclass(frozen=True)
class BagExpandResult:
    ok: bool
    error: str | None = None
    name: str = ""
    enhance: int = 0
    cost: int = 0
    coins: int = 0
    kinds: int = 0


@dataclass(frozen=True)
class DecomposeResult:
    ok: bool
    error: str | None = None
    name: str = ""
    quantity: int = 0
    enhance: int = 0
    essence: str = ""
    pity: int = 0
    pity_total: int = 0
    refund: int = 0
    coins: int = 0


@dataclass(frozen=True)
class DropGrant:
    name: str
    quantity: int
    ok: bool
    error: str | None = None
    current: int = 0
    payout: int = 0


@dataclass(frozen=True)
class DungeonRewardResult:
    ok: bool
    error: str | None = None
    exp: int = 0
    coins: int = 0
    coin_balance: int = 0
    levels_gained: int = 0
    level: int = 0
    current_exp: int = 0
    exp_to_next: int = 0
    items: tuple[DropGrant, ...] = ()


@dataclass(frozen=True)
class MarketOpResult:
    ok: bool
    error: str | None = None
    listing_id: int = 0
    name: str = ""
    quantity: int = 0
    unit_price: int = 0
    paid: int = 0
    fee: int = 0
    seller_gain: int = 0
    seller_openid: str = ""
    current: int = 0
    enhance: int = 0
    coins: int = 0


@dataclass(frozen=True)
class EnhanceResult:
    ok: bool
    error: str | None = None
    slot: str = ""
    name: str = ""
    old_level: int = 0
    new_level: int = 0
    cost: int = 0
    coins: int = 0
    failed_at: int | None = None
    refund: int = 0


@dataclass(frozen=True)
class TemperResult:
    ok: bool
    error: str | None = None
    slot: str = ""
    name: str = ""
    enhance: int = 0
    temper: int = 0
    added: int = 0
    cost: int = 0
    coins: int = 0


@dataclass(frozen=True)
class SellResult:
    ok: bool
    error: str | None = None
    name: str = ""
    enhance: int = 0
    quantity: int = 0
    price: int = 0
    refund: int = 0
    payout: int = 0
    coins: int = 0


@dataclass(frozen=True)
class SellLine:
    name: str
    enhance: int
    quantity: int
    payout: int


@dataclass(frozen=True)
class BatchSellResult:
    ok: bool
    error: str | None = None
    index: int = 0
    items: tuple[SellLine, ...] = ()
    quantity: int = 0
    payout: int = 0
    coins: int = 0


@dataclass(frozen=True)
class CraftResult:
    ok: bool
    error: str | None = None
    output: str = ""
    quantity: int = 0
    current: int = 0
    missing: str = ""
    enhance: int = 0
    refund: int = 0
    coins: int = 0


@dataclass(frozen=True)
class ExpResult:
    ok: bool
    error: str | None = None
    exp: int = 0
    level: int = 0
    current_exp: int = 0
    exp_to_next: int = 0
    levels_gained: int = 0
    levels_lost: int = 0


@dataclass(frozen=True)
class WorldBossStatus:
    used: int
    last_time: int


@dataclass(frozen=True)
class WorldBossResult:
    ok: bool
    error: str | None = None
    used: int = 0
    total_damage: int = 0
    cooldown_left: int = 0
    stamina_gained: int = 0
    stamina: int = 0


@dataclass(frozen=True)
class WarehouseRow:
    slot: int
    name: str
    quantity: int


@dataclass(frozen=True)
class PropResult:
    ok: bool
    error: str | None = None
    name: str = ""
    quantity: int = 0
    detail: str = ""
    blurb: str = ""


@dataclass(frozen=True)
class WorldShopResult:
    """世界币商城购买结果。"""

    ok: bool
    error: str | None = None
    name: str = ""
    quantity: int = 0
    cost: int = 0
    world_coins: int = 0


@dataclass(frozen=True)
class GiftBoxInfo:
    name: str = ""
    value: int = 0


@dataclass(frozen=True)
class BuyResult:
    ok: bool
    error: str | None = None
    name: str = ""
    cost: int = 0
    coins: int = 0
    quantity: int = 0


@dataclass(frozen=True)
class UserRow:
    openid: str
    level: int
    coins: int
    stamina: int
    special_stamina: int = 0


@dataclass(frozen=True)
class Account:
    openid: str
    user_id: str
    name: str
    created_at: int
