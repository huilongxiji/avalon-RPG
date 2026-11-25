"""玩家 HTTP 响应契约。核心结果复用服务层数据类，复合查询和战报在这里定义。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from ..rules.item import ItemDef
from ..rules.monster import DungeonDef, MonsterDef
from ..rules.prop import RecipeDef
from . import game_results as result
from .rules_admin import ItemDetail, StatInfo


class View(BaseModel):
    model_config = ConfigDict(extra='allow')


class PlayerPanel(View):
    openid: str
    level: int
    exp: int
    exp_to_next: int
    coins: int
    world_coins: int
    stamina: int
    special_stamina: int
    stats: dict[str, float]
    stat_meta: list[StatInfo] = []
    base_stats: dict[str, float] = {}
    stat_bonus: dict[str, float] = {}
    set_details: list[dict[str, Any]] = []
    damage_label: str
    pity: int
    capacity: int
    sets: dict[str, int]
    cards: list[tuple[str, int]]


class InventoryRow(BaseModel):
    index: int
    item_id: int
    name: str
    quantity: int
    enhance: int
    temper: int
    slot: str


class InventoryView(BaseModel):
    capacity: int
    items: list[InventoryRow]


class OwnedItem(View):
    item: ItemDef
    enhance: int
    temper: int
    stats: dict[str, float]
    stat_meta: list[StatInfo] = []
    detail: ItemDetail
    base_stats: dict[str, float] = {}
    next_stats: dict[str, float] = {}
    next_cost: int = 0
    total_cost: int = 0
    refund: int = 0
    temper_cap: int = 10
    sponsor_features: list[str] = []


class MarketDetail(View):
    id: int
    name: str
    quantity: int
    unit_price: int
    enhance: int
    temper: int = 0
    equipment: OwnedItem | None = None


class CheckinView(BaseModel):
    created: bool
    already_today: bool
    rank: int
    count: int
    stamina: int
    gained: int
    streak: int
    owed: int
    pity_gained: int
    pity: int
    bonus: dict[str, Any] | None = None


class EnhancePreview(BaseModel):
    name: str
    level: int
    chance: float
    cost: int


class TemperView(View):
    ok: bool
    slot: str
    name: str
    enhance: int
    temper: int
    added: int
    cost: int
    coins: int
    plan: dict[str, Any]
    temper_cap: int = 10


class CraftView(View):
    ok: bool
    output: str
    quantity: int
    current: int
    enhance: int
    refund: int
    coins: int
    inputs: list[dict[str, Any]] = []


class CombatTurn(View):
    round_no: int
    side: str
    damage: int
    total: int
    player_hp: int
    monster_hp: int
    parts: list[tuple[str, int]]
    notes: list[str]


class CombatNote(View):
    round_no: int
    turn_index: int
    phase: str
    side: str
    text: str


class CombatResult(View):
    won: bool
    draw: bool
    timeout: bool
    rounds: int
    player_first: bool
    player_hp: int
    monster_hp: int
    player_max_hp: int
    monster_max_hp: int
    turns: list[CombatTurn]
    notes: list[str]
    carry: dict[str, Any]
    triggered: dict[str, int]
    notes_timeline: list[CombatNote] = []


class DungeonRun(View):
    ok: bool
    dungeon: DungeonDef
    stamina: int
    remaining: int
    pity: int
    threshold: int
    # 每步 kind 不同（遇怪、连战、发奖、保底），保留结构化扩展字段。
    steps: list[dict[str, Any]]


class TowerFight(View):
    dungeon: DungeonDef
    monster: MonsterDef
    battle: CombatResult
    heal: int
    drops: list[str]


class TowerRun(View):
    ok: bool
    status: str
    used: int
    stamina: int
    paid: bool
    outcome: str
    lost_at: DungeonDef | None
    fights: list[TowerFight]
    grant: result.DungeonRewardResult | None


class BossRun(View):
    ok: bool
    damage: int
    record: result.WorldBossResult
    battle: CombatResult
    superuser: bool
    after_settle: bool


class PropUse(View):
    ok: bool
    name: str
    quantity: int
    detail: str
    blurb: str
    battle: DungeonRun | None


class GuideMonster(BaseModel):
    name: str
    kind: str
    level: int
    weight: int
    coins: int
    exp: int
    pool: list[tuple[str, float]]


class DungeonGuide(BaseModel):
    id: int
    name: str
    stamina: int
    monsters: list[GuideMonster]
    festival: tuple[str, int] | None
    pity: int
    threshold: int


class ShopEntry(View):
    id: int
    name: str
    price: int


class Shop(BaseModel):
    boxes: list[ShopEntry]
    world: list[ShopEntry]
    world_coins: int = 0


class RankRow(BaseModel):
    openid: str
    name: str
    damage: int


class RankView(BaseModel):
    items: list[RankRow]
    rules: dict[str, Any]


class MarketView(BaseModel):
    items: list[result.MarketListingView]
    rules: dict[str, Any]


class PropRecipe(BaseModel):
    id: int | None = None
    name: str
    inputs: list[dict[str, Any]]


class TowerStatus(BaseModel):
    status: str
    stamina: int
    used: int
    bonus: int


class BossStatus(BaseModel):
    used: int
    last_time: int
    limit: int
    cooldown_left: int


class Sent(BaseModel):
    sent: bool


class AdminResult(View):
    results: list[dict[str, Any]] | None = None


class ShopPurchase(View):
    ok: bool
    name: str
    quantity: int
    cost: int
    coins: int | None = None
    world_coins: int | None = None


RESPONSES = {
    'panel': PlayerPanel, 'profile': result.Account, 'profile_sync': result.Account,
    'checkin': CheckinView, 'makeup': result.MakeupResult, 'bag': InventoryView, 'sort': InventoryView,
    'bag_detail': OwnedItem, 'equipped': OwnedItem, 'equip': result.EquipResult, 'unequip': result.EquipResult,
    'enhance_preview': EnhancePreview, 'enhance': result.EnhanceResult, 'temper': TemperView,
    'sell': result.SellResult, 'sell_many': result.BatchSellResult, 'decompose': result.DecomposeResult,
    'craft': CraftView, 'expand': result.BagExpandResult, 'warehouse': list[result.WarehouseRow],
    'prop_use': PropUse, 'prop_craft': result.PropResult, 'redeem': result.PropResult,
    'shop_buy': ShopPurchase, 'dungeon': DungeonRun,
    'tower_status': TowerStatus, 'tower': TowerRun, 'boss_status': BossStatus, 'boss': BossRun,
    'rank': list[RankRow] | RankView, 'market': list[result.MarketListingView] | MarketView, 'market_detail': MarketDetail,
    'listing': result.MarketOpResult, 'buy': result.MarketOpResult, 'cancel': result.MarketOpResult,
    'dungeons': list[DungeonGuide], 'dungeon_guide': DungeonGuide, 'item': ItemDetail,
    'set': dict[str, Any], 'recipes': list[RecipeDef], 'prop_recipes': list[PropRecipe], 'shop': Shop,
    'admin_users': list[result.UserRow], 'admin_action': AdminResult, 'announcement': Sent, 'announcement_mark': Sent,
}
