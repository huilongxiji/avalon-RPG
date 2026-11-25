"""玩家的基础数值：账号、面板、代币、世界币、体力、经验和等级、保底、赞助卡（对应旧版 db.py 同名函数）。"""

from __future__ import annotations

from datetime import date, timedelta

from ..store.models.game import (
    Account,
    Announcement,
    BagExpand,
    Checkin,
    KnownGroup,
    Player,
    SponsorCard,
    Wallet,
)
from . import core, tuning
from .constants import EQUIP_SLOTS
from .results import Account as AccountView
from .results import AdjustResult, ExpResult, Panel, UserRow

Ok = tuple[bool, str | None, int]


def _bad_amount(amount: object) -> bool:
    return not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0


# ---------------------------------------------------------------- 账号、群、公告


async def touch_account(openid: str, user_id: str, name: str) -> AccountView:
    shown = name.strip() or "未知"
    async with core.tx():
        row = await Account.get_or_none(openid=openid)
        if row is None:
            row = await Account.create(openid=openid, user_id=user_id, name=shown)
        else:
            row.user_id, row.name = user_id, shown
            await row.save(update_fields=["user_id", "name"])
    return AccountView(openid=openid, user_id=user_id, name=shown, created_at=int(row.created_at.timestamp()))


async def remember_account(openid: str, user_id: str, name: str) -> None:
    """每条消息顺手登记：没有记录就新建；名称只在拿到非空昵称时更新。"""
    shown = name.strip()
    async with core.tx():
        row = await Account.get_or_none(openid=openid)
        if row is None:
            await Account.create(openid=openid, user_id=user_id, name=shown or "未知")
        else:
            row.user_id = user_id
            if shown:
                row.name = shown
            await row.save(update_fields=["user_id", "name"])


async def remember_group(group_id: int) -> None:
    async with core.tx():
        await KnownGroup.get_or_create(group_id=int(group_id))


async def list_known_groups() -> list[int]:
    return [int(g) for g in await KnownGroup.all().order_by("group_id").values_list("group_id", flat=True)]


async def unsent_announcement_groups(version: str) -> list[int]:
    sent = set(await Announcement.filter(version=version).values_list("group_id", flat=True))
    return [g for g in await list_known_groups() if g not in sent]


async def mark_announcement(version: str, group_id: int) -> None:
    async with core.tx():
        if not await Announcement.exists(version=version, group_id=int(group_id)):
            await Announcement.create(version=version, group_id=int(group_id))


async def announcement_sent(version: str, group_id: int) -> bool:
    return await Announcement.exists(version=version, group_id=int(group_id))


async def account_name(user_id: str = "", openid: str = "") -> str | None:
    """按用户 ID 反查登记的名称；用户 ID 查不到时再按 openid 查。"""
    for column, value in (("user_id", user_id), ("openid", openid)):
        if not value:
            continue
        row = await Account.filter(**{column: value}).first()
        if row is not None and row.name.strip():
            return row.name.strip()
    return None


async def openid_by_user_id(user_id: str) -> str | None:
    row = await Account.filter(user_id=user_id).first()
    return row.openid if row else None


# ---------------------------------------------------------------- 面板、玩家列表


def exp_to_next_for(level: int) -> int:
    previous = 0
    for current_level in range(1, level + 1):
        previous = max(1, int(tuning.formula('exp_to_next', level=current_level, previous=previous)))
    return previous


async def get_panel(openid: str) -> Panel | None:
    player = await core.get_player(openid)
    if player is None:
        return None
    w = await core.wallet(openid)
    eq = await core.equipped(openid)
    slots: dict[str, object] = {}
    for slot in EQUIP_SLOTS:
        e = eq[slot]
        slots[slot] = core.item_name(e.item_id) or "无"
        slots[f"{slot}_enhance"] = e.enhance if e.item_id is not None else 0
        slots[f"{slot}_temper"] = e.temper if e.item_id is not None else 0
    return Panel(openid=openid, level=player.level, exp=player.exp, exp_to_next=exp_to_next_for(player.level),
                 hp=player.hp, atk=player.atk, defense=player.defense, agi=player.agi, mp=player.mp,
                 penetration=player.penetration, stamina=player.stamina, special_stamina=player.special_stamina,
                 coins=int(w.coins), world_coins=int(w.world_coins), **slots)  # type: ignore[arg-type]


async def user_exists(openid: str) -> bool:
    return await Player.exists(openid=openid)


async def list_user_qqs() -> list[str]:
    return list(await Player.all().order_by("openid").values_list("openid", flat=True))


async def list_users() -> list[UserRow]:
    players = await Player.all().order_by("-level", "openid")
    coins = dict(await Wallet.all().values_list("player_id", "coins"))
    return [UserRow(openid=p.openid, level=p.level, coins=int(coins.get(p.openid, 0)), stamina=p.stamina,
                    special_stamina=p.special_stamina) for p in players]


# ---------------------------------------------------------------- 代币、世界币


async def _add_coins(openid: str, amount: int) -> int:
    w = await core.wallet(openid)
    w.coins = int(w.coins) + amount
    await w.save(update_fields=["coins"])
    return int(w.coins)


async def add_coins(openid: str, amount: int) -> Ok:
    if _bad_amount(amount):
        return False, "bad_qty", 0
    async with core.tx():
        if not await Player.exists(openid=openid):
            return False, "no_user", 0
        return True, None, await _add_coins(openid, amount)


async def remove_coins(openid: str, amount: int | None) -> AdjustResult:
    if amount is not None and _bad_amount(amount):
        return AdjustResult(ok=False, error="bad_qty")
    async with core.tx():
        if not await Player.exists(openid=openid):
            return AdjustResult(ok=False, error="no_user")
        w = await core.wallet(openid)
        take = int(w.coins) if amount is None else min(int(w.coins), amount)
        w.coins = int(w.coins) - take
        await w.save(update_fields=["coins"])
        return AdjustResult(ok=True, removed=take, current=int(w.coins))


async def _add_world_coins(openid: str, amount: int) -> int:
    w = await core.wallet(openid)
    w.world_coins = int(w.world_coins) + amount
    await w.save(update_fields=["world_coins"])
    return int(w.world_coins)


async def add_world_coins(openid: str, amount: int) -> Ok:
    """加世界币（世界BOSS排名奖励等），无上限。"""
    if _bad_amount(amount):
        return False, "bad_qty", 0
    async with core.tx():
        if not await Player.exists(openid=openid):
            return False, "no_user", 0
        return True, None, await _add_world_coins(openid, amount)


async def remove_world_coins(openid: str, amount: int | None) -> AdjustResult:
    """扣除世界币，最少扣到 0；amount 为 None 时清零。"""
    if amount is not None and _bad_amount(amount):
        return AdjustResult(ok=False, error="bad_qty")
    async with core.tx():
        if not await Player.exists(openid=openid):
            return AdjustResult(ok=False, error="no_user")
        w = await core.wallet(openid)
        take = int(w.world_coins) if amount is None else min(int(w.world_coins), amount)
        w.world_coins = int(w.world_coins) - take
        await w.save(update_fields=["world_coins"])
    return AdjustResult(ok=True, removed=take, current=int(w.world_coins))


# ---------------------------------------------------------------- 体力


async def add_stamina(openid: str, amount: int) -> Ok:
    """加普通体力，最多到 2000 上限；周卡/月卡/年卡体力用 add_special_stamina。"""
    if _bad_amount(amount):
        return False, "bad_qty", 0
    async with core.tx():
        p = await core.get_player(openid)
        if p is None:
            return False, "no_user", 0
        p.stamina = max(p.stamina, min(tuning.value('stamina_cap'), p.stamina + amount))
        await p.save(update_fields=["stamina"])
        return True, None, p.stamina


async def add_special_stamina(openid: str, amount: int) -> Ok:
    """加特殊体力（周卡/月卡/年卡），无上限。"""
    if _bad_amount(amount):
        return False, "bad_qty", 0
    async with core.tx():
        p = await core.get_player(openid)
        if p is None:
            return False, "no_user", 0
        p.special_stamina += amount
        await p.save(update_fields=["special_stamina"])
        return True, None, p.special_stamina


async def _refund_stamina(p: Player, amount: int) -> int:
    to_normal = max(0, min(tuning.value('stamina_cap') - p.stamina, amount))
    p.stamina += to_normal
    p.special_stamina += amount - to_normal
    await p.save(update_fields=["stamina", "special_stamina"])
    return p.stamina + p.special_stamina


async def refund_stamina(openid: str, amount: int) -> Ok:
    """退回体力：先回普通体力到 2000 上限，超出部分回特殊体力，总量不丢失。"""
    if _bad_amount(amount):
        return False, "bad_qty", 0
    async with core.tx():
        p = await core.get_player(openid)
        if p is None:
            return False, "no_user", 0
        return True, None, await _refund_stamina(p, amount)


async def _spend_stamina(p: Player, amount: int) -> Ok:
    total = p.stamina + p.special_stamina
    if total < amount:
        return False, "no_stamina", total
    take_normal = min(p.stamina, amount)
    p.stamina -= take_normal
    p.special_stamina -= amount - take_normal
    await p.save(update_fields=["stamina", "special_stamina"])
    return True, None, total - amount


async def spend_stamina(openid: str, amount: int) -> Ok:
    """消耗体力：先扣普通体力，不足部分用特殊体力补足。返回剩余总量。"""
    if _bad_amount(amount):
        return False, "bad_qty", 0
    async with core.tx():
        p = await core.get_player(openid)
        if p is None:
            return False, "no_user", 0
        return await _spend_stamina(p, amount)


async def remove_stamina(openid: str, amount: int | None) -> AdjustResult:
    if amount is not None and _bad_amount(amount):
        return AdjustResult(ok=False, error="bad_qty")
    async with core.tx():
        p = await core.get_player(openid)
        if p is None:
            return AdjustResult(ok=False, error="no_user")
        total = p.stamina + p.special_stamina
        take = total if amount is None else min(total, amount)
        take_normal = min(p.stamina, take)
        p.stamina -= take_normal
        p.special_stamina -= take - take_normal
        await p.save(update_fields=["stamina", "special_stamina"])
        return AdjustResult(ok=True, removed=take, current=total - take)


# ---------------------------------------------------------------- 经验和等级


async def _apply_exp(p: Player, exp: int) -> tuple[int, int, int, int]:
    """加经验并升级（每级 +5 生命、+1 攻击）。返回（等级，当前经验，升级所需，升了几级）。"""
    level = p.level
    current_exp = p.exp + exp
    need = exp_to_next_for(level)
    gained = 0
    while current_exp >= need:
        current_exp -= need
        level += 1
        gained += 1
        p.hp += tuning.value('hp_per_level')
        p.atk += tuning.value('atk_per_level')
        need = exp_to_next_for(level)
    p.level, p.exp = level, current_exp
    await p.save(update_fields=["level", "exp", "hp", "atk"])
    return level, current_exp, need, gained


async def add_exp(openid: str, amount: int) -> ExpResult:
    if _bad_amount(amount):
        return ExpResult(ok=False, error="bad_qty")
    async with core.tx():
        p = await core.get_player(openid)
        if p is None:
            return ExpResult(ok=False, error="no_user")
        level, current_exp, need, gained = await _apply_exp(p, amount)
    return ExpResult(ok=True, exp=amount, level=level, current_exp=current_exp, exp_to_next=need,
                     levels_gained=gained)


async def remove_exp(openid: str, amount: int | None) -> ExpResult:
    if amount is not None and _bad_amount(amount):
        return ExpResult(ok=False, error="bad_qty")
    async with core.tx():
        p = await core.get_player(openid)
        if p is None:
            return ExpResult(ok=False, error="no_user")
        level, current_exp = p.level, p.exp
        taken = lost = 0
        if amount is None:
            taken = sum(exp_to_next_for(lv) for lv in range(1, level)) + current_exp
            lost = max(0, level - 1)
            p.hp -= tuning.value('hp_per_level') * lost
            p.atk -= tuning.value('atk_per_level') * lost
            level, current_exp = 1, 0
        else:
            remain = amount
            while remain > 0:
                if current_exp > 0:
                    take = min(current_exp, remain)
                    current_exp -= take
                    remain -= take
                    taken += take
                    continue
                if level <= 1:
                    break
                level -= 1
                lost += 1
                p.hp -= tuning.value('hp_per_level')
                p.atk -= tuning.value('atk_per_level')
                current_exp = exp_to_next_for(level)
        p.level, p.exp = level, current_exp
        await p.save(update_fields=["level", "exp", "hp", "atk"])
    return ExpResult(ok=True, exp=taken, level=level, current_exp=current_exp, exp_to_next=exp_to_next_for(level),
                     levels_lost=lost)


# ---------------------------------------------------------------- 保底


async def get_pity(openid: str) -> int:
    return await core.read_pity(openid)


async def set_pity(openid: str, value: int) -> int:
    async with core.tx():
        if not await Player.exists(openid=openid):
            return 0
        return await core.write_pity(openid, value)


async def adjust_pity(openid: str, delta: int) -> int:
    """在当前保底值上加减 delta（最低 0）：副本结算按增量写回，不覆盖战斗期间别处的改动。"""
    async with core.tx():
        if not await Player.exists(openid=openid):
            return 0
        return await core.write_pity(openid, await core.read_pity(openid) + int(delta))


async def add_pity(openid: str, amount: int) -> Ok:
    if _bad_amount(amount):
        return False, "bad_qty", 0
    async with core.tx():
        if not await Player.exists(openid=openid):
            return False, "no_user", 0
        return True, None, await core.write_pity(openid, await core.read_pity(openid) + amount)


async def remove_pity(openid: str, amount: int | None) -> AdjustResult:
    """扣除副本保底，最少扣到 0；amount 为 None 时清零。"""
    if amount is not None and _bad_amount(amount):
        return AdjustResult(ok=False, error="bad_qty")
    async with core.tx():
        if not await Player.exists(openid=openid):
            return AdjustResult(ok=False, error="no_user")
        held = await core.read_pity(openid)
        take = held if amount is None else min(held, amount)
        stored = await core.write_pity(openid, held - take)
    return AdjustResult(ok=True, removed=take, current=stored)


# ---------------------------------------------------------------- 赞助卡、背包种类上限

_CARD_KIND_BONUS = {"week": "week_card_extra_kinds", "month": "month_card_extra_kinds", "year": "year_card_extra_kinds"}


async def grant_sponsor_card(openid: str, kind: str, days: int) -> tuple[bool, str | None, str, int]:
    """顺延有效期。返回是否成功、错误、到期日、含今天在内的剩余天数。"""
    if kind not in _CARD_KIND_BONUS or _bad_amount(days):
        return False, "bad_qty", "", 0
    today = core.today()
    async with core.tx():
        if not await Player.exists(openid=openid):
            return False, "no_user", "", 0
        row = await SponsorCard.get_or_none(player_id=openid, kind=kind)
        if row is not None:
            start = row.expires_on if row.expires_on >= today else today - timedelta(days=1)
            expires = start + timedelta(days=days)
            row.expires_on = expires
            await row.save(update_fields=["expires_on"])
        else:
            expires = today + timedelta(days=days - 1)
            await SponsorCard.create(player_id=openid, kind=kind, expires_on=expires)
    return True, None, expires.isoformat(), (expires - today).days + 1


async def checked_in_today(openid: str) -> bool:
    row = await Checkin.get_or_none(player_id=openid)
    return row is not None and row.last_date == core.today()


async def active_sponsor_cards(openid: str) -> list[tuple[str, int]]:
    today: date = core.today()
    rows = await SponsorCard.filter(player_id=openid).order_by("id")
    return [(r.kind, (r.expires_on - today).days + 1) for r in rows if r.expires_on >= today]


async def bag_expand_count(openid: str) -> int:
    return await BagExpand.filter(player_id=openid).count()


async def max_item_kinds(openid: str) -> int:
    """背包种类上限：基础 50，周卡 +20，月卡 +50，年卡不限，每次隐秘宝石扩容 +2。"""
    extra = sum(tuning.value(_CARD_KIND_BONUS[kind]) for kind, _ in await active_sponsor_cards(openid)
                if kind in _CARD_KIND_BONUS)
    return tuning.value('max_item_kinds') + extra + await bag_expand_count(openid) * tuning.value('bag_expand_slots')


