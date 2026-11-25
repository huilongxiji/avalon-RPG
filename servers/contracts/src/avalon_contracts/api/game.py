"""M5 玩家接口契约。API 网关、逻辑服务共用路由和请求模型，bot 只依赖本包。

价格、伤害、奖励、超管身份不接受请求体声明，均在服务端计算或从可信身份头取得。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Positive = Annotated[int, Field(strict=True, gt=0, le=1_000_000)]
Slot = Literal["weapon", "armor", "bracelet", "necklace", "gem"]


class RequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Empty(RequestBody):
    pass


class Index(RequestBody):
    index: Positive


class Quantity(Index):
    quantity: Positive = 1


class Slots(RequestBody):
    indices: list[Positive] = Field(min_length=1, max_length=200)


class EquipSlot(RequestBody):
    slot: Slot


class Enhance(EquipSlot):
    target: Annotated[int, Field(strict=True, ge=1, le=100)] | None = None
    confirmed: bool = False
    expected_level: Annotated[int, Field(strict=True, ge=0)] | None = None
    expected_name: str | None = Field(default=None, min_length=1, max_length=128)


class Recipe(RequestBody):
    recipe_id: Positive


class UseProp(RequestBody):
    key: str = Field(min_length=1, max_length=128)
    quantity: Positive = 1
    choice: str = Field(default="", max_length=128)
    # 聊天附加参数由逻辑层按道具效果解释；显式 API 客户端使用 quantity/choice。
    argument: str | None = Field(default=None, max_length=128)


class CraftProp(RequestBody):
    name: str = Field(min_length=1, max_length=128)
    quantity: Positive = 1


class Redeem(RequestBody):
    code: str = Field(min_length=1, max_length=64)


class Makeup(RequestBody):
    days: Positive | None = None


class Tower(RequestBody):
    confirmed: bool = False


class Listing(Quantity):
    unit_price: Annotated[int, Field(strict=True, gt=0, le=1_000_000_000)]


class BuyListing(RequestBody):
    quantity: Positive | None = None


class ShopBuy(RequestBody):
    kind: Literal["box", "world"]
    index: Positive
    quantity: Positive = 1


class Profile(RequestBody):
    user_id: str = Field(min_length=1, max_length=64)
    name: str = Field(default="", max_length=128)
    group_id: Annotated[int, Field(strict=True, gt=0)] | None = None


class AdminAction(RequestBody):
    action: Literal["coins", "world_coins", "stamina", "exp", "pity", "tower", "item", "items",
                    "remove_item", "destroy_equipped", "prop", "remove_prop", "redeem_code", "makeup",
                    "force", "festival", "card", "gem", "remove_gem"]
    targets: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(default_factory=list, max_length=500)
    all_players: bool = False
    quantity: Annotated[int, Field(strict=True, ge=-1_000_000_000, le=1_000_000_000)] | None = None
    remove_all: bool = False
    name: str = Field(default="", max_length=128)
    item_ids: list[Annotated[int, Field(strict=True, ge=0)]] = Field(default_factory=list, max_length=200)
    enhance_level: Annotated[int, Field(strict=True, ge=0, le=100)] | None = None
    slot: Slot | None = None
    kind: Literal["week", "month", "year"] | None = None
    enabled: bool = True
    features: list[Literal["pity", "stamina", "boss", "drop_pct", "coin_pct", "exp_pct", "bless", "chain", "explore"]] = Field(default_factory=list)


class Announcement(RequestBody):
    version: str = Field(min_length=1, max_length=32)
    group_id: Annotated[int, Field(strict=True, gt=0)]


@dataclass(frozen=True)
class Operation:
    key: str
    method: str
    path: str
    title: str
    body: type[RequestBody] | None = None
    admin: bool = False


OPERATIONS = (
    Operation("panel", "GET", "/players/{openid}", "玩家面板"),
    Operation("profile", "GET", "/players/{openid}/profile", "个人信息"),
    Operation("profile_sync", "POST", "/players/{openid}/profile", "同步账号和群", Profile),
    Operation("checkin", "POST", "/players/{openid}/checkin", "签到及卡片奖励", Empty),
    Operation("makeup", "POST", "/players/{openid}/checkin/makeup", "超管补签", Makeup, admin=True),
    Operation("bag", "GET", "/players/{openid}/bag", "背包"),
    Operation("bag_detail", "GET", "/players/{openid}/bag/{index}", "背包装备详情"),
    Operation("equipped", "GET", "/players/{openid}/equipped/{slot}", "已穿装备详情"),
    Operation("sort", "POST", "/players/{openid}/bag/sort", "整理背包", Empty),
    Operation("equip", "POST", "/players/{openid}/equip", "穿戴", Index),
    Operation("unequip", "POST", "/players/{openid}/unequip", "卸下", EquipSlot),
    Operation("enhance_preview", "GET", "/players/{openid}/enhance/preview", "强化预览"),
    Operation("enhance", "POST", "/players/{openid}/enhance", "强化", Enhance),
    Operation("temper", "POST", "/players/{openid}/temper", "淬炼", EquipSlot),
    Operation("sell", "POST", "/players/{openid}/sell", "出售", Quantity),
    Operation("sell_many", "POST", "/players/{openid}/sell/batch", "批量出售", Slots),
    Operation("decompose", "POST", "/players/{openid}/decompose", "分解", Quantity),
    Operation("craft", "POST", "/players/{openid}/craft", "装备合成", Recipe),
    Operation("expand", "POST", "/players/{openid}/expand", "背包扩容", Index),
    Operation("warehouse", "GET", "/players/{openid}/warehouse", "道具仓库"),
    Operation("prop_use", "POST", "/players/{openid}/props/use", "使用道具及跨界挑战", UseProp),
    Operation("prop_craft", "POST", "/players/{openid}/props/craft", "道具合成", CraftProp),
    Operation("redeem", "POST", "/players/{openid}/props/redeem", "兑换码", Redeem),
    Operation("shop_buy", "POST", "/players/{openid}/shop/buy", "商城购买", ShopBuy),
    Operation("dungeon", "POST", "/players/{openid}/dungeons/{id}/challenge", "副本挑战", Empty),
    Operation("tower_status", "GET", "/players/{openid}/tower", "爬塔次数和费用"),
    Operation("tower", "POST", "/players/{openid}/tower", "爬塔", Tower),
    Operation("boss_status", "GET", "/players/{openid}/world-boss", "世界 BOSS 次数和冷却"),
    Operation("boss", "POST", "/players/{openid}/world-boss", "世界 BOSS 挑战", Empty),
    Operation("rank", "GET", "/world-boss/rank", "世界排行榜"),
    Operation("market", "GET", "/market", "玩家市场"),
    Operation("market_detail", "GET", "/market/{id}", "挂单详情"),
    Operation("listing", "POST", "/market", "上架", Listing),
    Operation("buy", "POST", "/market/{id}/buy", "购买挂单", BuyListing),
    Operation("cancel", "DELETE", "/market/{id}", "下架挂单"),
    Operation("dungeons", "GET", "/dungeons", "副本列表"),
    Operation("dungeon_guide", "GET", "/dungeons/{id}", "副本图鉴"),
    Operation("item", "GET", "/items/{id}", "物品图鉴"),
    Operation("set", "GET", "/sets/{name}", "套装图鉴"),
    Operation("recipes", "GET", "/recipes", "装备配方"),
    Operation("prop_recipes", "GET", "/props/recipes", "道具配方"),
    Operation("shop", "GET", "/shop", "商城商品和价格"),
    Operation("admin_users", "GET", "/admin/players", "超管用户列表", admin=True),
    Operation("admin_action", "POST", "/admin/players/actions", "超管操作", AdminAction, admin=True),
    Operation("announcement", "GET", "/bot/announcements/{version}/{group_id}", "公告发送记录"),
    Operation("announcement_mark", "POST", "/bot/announcements", "记录公告发送", Announcement),
)

BY_KEY = {operation.key: operation for operation in OPERATIONS}
