"""赞助：周卡、月卡、年卡和定制宝石（对应旧版 sponsor 插件和 db.py 的赞助部分）。

- 卡片：发卡时给特殊体力和保底，有效期内每次签到额外给体力、保底、免费爬塔；年卡另有多项加成（见各玩法）。
- 定制宝石：超管按名字做一颗只给这个人用的宝石（规则库里新增一件赞助宝石装备，马上生效），
  功能任选：保底、体力、必遇、掉率、祝福、金币、经验、连战、探寻。穿在宝石位、归属本人时才生效。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace

from avalon_contracts.rules.item import ItemDef

from ..rules.store import RuleData
from ..store.models.game import Equipped, InventoryItem, Player, SponsorGem, TowerDaily
from . import bag, core, economy, tuning

BOSS_EVERY = 8
FEATURE_KEY = {"保底": "pity", "减少副本体力消耗": "stamina", "体力": "stamina", "必遇": "boss", "掉率": "drop_pct",
               "装备掉率": "drop_pct", "祝福": "bless", "金币": "coin_pct", "副本金币": "coin_pct", "经验": "exp_pct",
               "副本经验": "exp_pct", "连战": "chain", "探寻": "explore"}
FEATURE_LABEL = {"pity": "保底值", "stamina": "体力", "boss": "必遇", "drop_pct": "掉率", "bless": "祝福",
                 "chain": "连战", "explore": "探寻", "coin_pct": "金币", "exp_pct": "经验"}
GEM_BONUS = {"drop_pct": 50, "coin_pct": 20, "exp_pct": 10}
CARD_DAYS = {"week": 7, "month": 30, "year": 365}
CARD_GRANT = {"week": (80, 25), "month": (450, 150), "year": (6000, 200)}      # 发卡时：特殊体力、保底
CARD_LABEL = {"week": "周卡", "month": "月卡", "year": "年卡"}
CARD_DAILY = {"week": (15, 0, 0), "month": (20, 5, 1), "year": (30, 15, 2)}   # 每次签到：体力、保底、免费爬塔


@dataclass(frozen=True)
class CardBonus:
    stamina: int = 0
    pity: int = 0
    tower_free: int = 0
    lines: tuple[str, ...] = ()
    stamina_total: int | None = None      # 发放后最新的普通体力 / 保底；没发对应奖励时为 None
    pity_total: int | None = None


# ---------------------------------------------------------------- 定制宝石记录


async def sponsor_gem(name: str) -> SponsorGem | None:
    return await SponsorGem.get_or_none(name=name.strip())


def feature_descriptions(gem: SponsorGem) -> list[str]:
    """装备卡片的功能说明来自实际宝石和当前规则，前端只负责排版。"""
    lines = []
    if gem.pity:
        normal, reduced = tuning.value('pity_per_dungeon'), tuning.value('pity_gem_per_dungeon')
        lines.append(f'保底值：每个副本编号所需保底值由 {normal} 降为 {reduced}')
    if gem.stamina:
        lines.append('体力：副本战斗胜利后随机获得0~2点体力')
    if gem.boss:
        lines.append(f"必遇：每 {tuning.value('boss_every')} 次战斗必定遇到 1 次 BOSS")
    if gem.drop_pct or gem.hidden_pct:
        lines.append(f'掉率：隐秘遭遇率+{gem.hidden_pct}%。特殊掉率+{gem.drop_pct}%。')
    if gem.bless:
        lines.append('祝福：战斗等级差-2，获得额外副本经验（按当前祝福公式计算）')
    if gem.chain:
        lines.append(f"连战：副本挑战后 {tuning.value('chain_chance_pct')}% 概率连续战斗。")
    if gem.explore:
        chance = tuning.value('explore_chance_pct')
        lines.append(f"探寻：战斗胜利后，{chance}%获得{tuning.value('explore_exp_pct')}%额外经验，"
                     f"{chance}%获得{tuning.value('explore_coin_pct')}%额外代币，{chance}%获得1点体力，{chance}%获得1点保底值。")
    if gem.coin_pct:
        lines.append(f'金币：副本代币+{gem.coin_pct}%')
    if gem.exp_pct:
        lines.append(f'经验：副本经验+{gem.exp_pct}%')
    return lines


async def equipped_gem(openid: str) -> SponsorGem | None:
    """玩家身上穿着、归属本人的定制宝石；没有就是 None。"""
    worn = await bag.get_equipped(openid, "gem")
    if worn is None:
        return None
    gem = await sponsor_gem(worn[0])
    return gem if gem is not None and gem.player_id == openid else None  # type: ignore[attr-defined]


async def year_card_active(openid: str) -> bool:
    return any(kind == "year" for kind, _ in await economy.active_sponsor_cards(openid))


async def advance_sponsor_gem_boss(name: str, every: int | None = None) -> tuple[bool, int]:
    """必遇计数 +1；满 every 次时归零并返回 (True, 0)。"""
    every = tuning.value('boss_every') if every is None else every
    if not isinstance(every, int) or every <= 0:
        return False, 0
    async with core.tx():
        gem = await sponsor_gem(name)
        if gem is None or not gem.boss:
            return False, 0
        forced = gem.boss_fights + 1 >= every
        gem.boss_fights = 0 if forced else gem.boss_fights + 1
        await gem.save(update_fields=["boss_fights"])
        return forced, gem.boss_fights


async def note_main_fight(openid: str) -> tuple[str, int, int] | None:
    """勾了必遇时每 8 次副本主战强制遇到一次 BOSS；触发时返回 (宝石名, 0, 周期)。"""
    gem = await equipped_gem(openid)
    if gem is None or not gem.boss:
        return None
    forced, fights = await advance_sponsor_gem_boss(gem.name, tuning.value('boss_every'))
    return (gem.name, fights, tuning.value('boss_every')) if forced else None


async def boss_pity_progress(openid: str) -> tuple[int, int] | None:
    gem = await equipped_gem(openid)
    if gem is None or not gem.boss:
        return None
    return gem.boss_fights, tuning.value('boss_every')


async def on_fight_win(openid: str, refund_stamina: bool) -> tuple[str, int | None, int | None] | None:
    """勾了体力时，副本战斗胜利后随机得 0~2 点体力。"""
    gem = await equipped_gem(openid)
    if gem is None:
        return None
    stamina_add = None
    if refund_stamina and gem.stamina:
        stamina_add = random.randrange(3)
        if stamina_add:
            await economy.add_stamina(openid, stamina_add)
    return None if stamina_add is None else (gem.name, None, stamina_add)


async def register_sponsor_gem(openid: str, name: str, *, pity: bool, stamina: bool, boss: bool, hidden_pct: int = 0,
                               drop_pct: int = 0, coin_pct: int = 0, exp_pct: int = 0, bless: bool = False,
                               chain: bool = False, explore: bool = False) -> tuple[bool, str | None]:
    name = name.strip()
    if not name or not (pity or stamina or boss or hidden_pct or drop_pct or coin_pct or exp_pct or bless or chain
                        or explore):
        return False, "bad_name"
    async with core.tx():
        if not await Player.exists(openid=openid):
            return False, "no_user"
        if await SponsorGem.exists(name=name):
            return False, "exists"
        await SponsorGem.create(name=name, player_id=openid, pity=pity, stamina=stamina, boss=boss, boss_fights=0,
                                hidden_pct=hidden_pct, drop_pct=drop_pct, coin_pct=coin_pct, exp_pct=exp_pct,
                                bless=bless, chain=chain, explore=explore)
    return True, None


async def delete_sponsor_gem(name: str) -> None:
    async with core.tx():
        await SponsorGem.filter(name=name.strip()).delete()


async def remove_sponsor_gem(name: str) -> int:
    """把这颗宝石从所有玩家的背包和宝石栏里拿走，连同宝石记录一起删掉。返回拿走了几处。"""
    name = name.strip()
    found = core.item_by_name(name)
    async with core.tx():
        removed = 0
        if found is not None:
            removed += await InventoryItem.filter(item_id=found.id, quantity__gt=0).count()
            await InventoryItem.filter(item_id=found.id).delete()
            removed += await Equipped.filter(slot="gem", item_id=found.id).update(item_id=None, enhance=0, temper=0)
        await SponsorGem.filter(name=name).delete()
    return removed


# ---------------------------------------------------------------- 卡片


async def _grant_daily(openid: str, stamina: int, pity: int, tower_free: int) -> CardBonus:
    lines: list[str] = []
    stamina_total: int | None = None
    pity_total: int | None = None
    if stamina:
        player = await core.get_player(openid)
        before = player.stamina if player else 0
        ok, _, stamina_total = await economy.add_stamina(openid, stamina)
        added = stamina_total - before if ok else 0
        if added < stamina:
            lines.append(f"体力已达上限 {tuning.value('stamina_cap')}，卡片额外体力实际到账 **{max(0, added)}**")
        stamina = max(0, added)
        if not ok:
            stamina_total = None
    if pity:
        ok, _, stored = await economy.add_pity(openid, pity)
        pity_total = stored if ok else None
    if tower_free:
        await add_tower_free(openid, tower_free)
    return CardBonus(stamina=stamina, pity=pity, tower_free=tower_free, lines=tuple(lines),
                     stamina_total=stamina_total, pity_total=pity_total)


@core.atomic
async def checkin_bonus(openid: str) -> CardBonus:
    """签到后发放卡片每日奖励。"""
    active = dict(await economy.active_sponsor_cards(openid))
    stamina = pity = tower_free = 0
    lines: list[str] = []
    for kind in ("week", "month", "year"):
        if kind not in active:
            continue
        s, p, t = tuning.value('card_daily')[kind]
        stamina += s
        pity += p
        tower_free += t
        if kind == "week":
            lines.append(f"周卡剩余 **{active[kind]}** 天，额外体力 **{s}**")
        else:
            lines.append(f"{CARD_LABEL[kind]}剩余 **{active[kind]}** 天，额外体力 **{s}**、保底 **{p}**、免费爬塔 **{t}** 次")
    granted = await _grant_daily(openid, stamina, pity, tower_free)
    return replace(granted, lines=tuple(lines) + granted.lines)


@core.atomic
async def grant_card_daily_bonus(openid: str, kind: str) -> CardBonus:
    return await _grant_daily(openid, *tuning.value('card_daily')[kind])


@core.atomic
async def grant_card(openid: str, kind: str) -> tuple[bool, str | None, str]:
    """发卡：顺延有效期，给特殊体力和保底；发卡前没有这张卡且今天已签到，补发当日签到奖励。"""
    stamina, pity = tuning.value('card_grant')[kind]
    held_before = any(k == kind for k, _ in await economy.active_sponsor_cards(openid))
    checked_today = await economy.checked_in_today(openid)
    ok, error, _expires, left = await economy.grant_sponsor_card(openid, kind, tuning.value('card_days')[kind])
    if not ok:
        return False, error, ""
    await economy.add_special_stamina(openid, stamina)
    await economy.add_pity(openid, pity)
    text = f"{CARD_LABEL[kind]}剩余 **{left}** 天，体力 **{stamina}**，保底 **{pity}**"
    if not held_before and checked_today:
        daily = await grant_card_daily_bonus(openid, kind)
        parts = []
        if daily.stamina:
            parts.append(f"体力 **{daily.stamina}**")
        if daily.pity:
            parts.append(f"保底 **{daily.pity}**")
        if daily.tower_free:
            parts.append(f"免费爬塔 **{daily.tower_free}** 次")
        text += f"，补发当日签到奖励：{'、'.join(parts)}"
    return True, None, text


async def add_tower_free(openid: str, amount: int = 1) -> bool:
    """今天额外的免费爬塔次数。"""
    if not isinstance(amount, int) or amount <= 0:
        return False
    async with core.tx():
        if not await Player.exists(openid=openid):
            return False
        row = await TowerDaily.get_or_none(player_id=openid, day=core.today())
        if row is None:
            await TowerDaily.create(player_id=openid, day=core.today(), used=0, paid=0, bonus_free=amount)
        else:
            row.bonus_free += amount
            await row.save(update_fields=["bonus_free"])
    return True


# ---------------------------------------------------------------- 做 / 删定制宝石（超管）


def parse_gem_args(tokens: list[str]) -> tuple[str, dict[str, bool]] | str:
    """从末尾往回读功能，剩下的就是宝石名。返回 (名字, 功能) 或错误说明。"""
    tokens = list(tokens)
    picked: list[str] = []
    while tokens and tokens[-1] in FEATURE_KEY:
        key = FEATURE_KEY[tokens.pop()]
        if key in picked:
            return f"功能重复：{FEATURE_LABEL[key]}"
        picked.append(key)
    name = " ".join(tokens).strip()
    if not name or not picked or name == "无":
        return "用法: 定制宝石 <@/openid> <宝石名> <功能> [功能] ...（功能不填数量）"
    return name, {key: key in picked for key in FEATURE_LABEL}


def _with_item(name: str):
    def mutate(data: RuleData) -> RuleData:
        new_id = max((i.id for i in data.items), default=0) + 1
        item = ItemDef(id=new_id, name=name, slot="gem", price=0, sponsor=True)
        return replace(data, items=[*data.items, item])
    return mutate


def _without_item(name: str):
    def mutate(data: RuleData) -> RuleData:
        return replace(data, items=[i for i in data.items if i.name != name])
    return mutate


@core.rollback_result
@core.atomic_rules
async def grant_named_gem(openid: str, name: str, flags: dict[str, bool]) -> tuple[bool, str | None, str]:
    from ..rules import editing

    if core.item_by_name(name) is not None:
        return False, "dup_item", ""
    if await sponsor_gem(name) is not None:
        return False, "exists", ""
    await editing.apply_to_live(_with_item(name), actor="定制宝石", note=f"定制宝石 {name}")
    ok, error = await register_sponsor_gem(
        openid, name, pity=flags["pity"], stamina=flags["stamina"], boss=flags["boss"],
        hidden_pct=tuning.value('gem_bonus')["drop_pct"] if flags["drop_pct"] else 0,
        drop_pct=tuning.value('gem_bonus')["drop_pct"] if flags["drop_pct"] else 0,
        coin_pct=tuning.value('gem_bonus')["coin_pct"] if flags["coin_pct"] else 0,
        exp_pct=tuning.value('gem_bonus')["exp_pct"] if flags["exp_pct"] else 0,
        bless=flags["bless"], chain=flags["chain"], explore=flags["explore"])
    if not ok:
        raise core.Rollback((False, error, ""))
    result = await bag.add_item(openid, name, 1)
    if not result.ok:
        raise core.Rollback((False, result.error or "write", ""))
    labels = [label for key, label in FEATURE_LABEL.items() if flags[key]]
    return True, None, f"**{name}** 已放入背包，功能 {'、'.join(labels)}。穿上后生效，不能上架"


@core.atomic_rules
async def remove_named_gem(name: str) -> tuple[bool, str | None, str]:
    from ..rules import editing

    if await sponsor_gem(name) is None:
        return False, "no_gem", ""
    taken = await remove_sponsor_gem(name)
    if core.item_by_name(name) is not None:
        await editing.apply_to_live(_without_item(name), actor="定制宝石", note=f"删除定制宝石 {name}")
    return True, None, f"**{name}** 已删除，从 **{taken}** 处背包/宝石栏拿走"


