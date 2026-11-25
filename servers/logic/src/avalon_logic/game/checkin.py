"""签到、补签（对应旧版 db.py 的 checkin / makeup_checkin）。

- 每天签到一次：体力 + (100 + 等级 + 累计签到次数)，年卡再 +10%，普通体力最多 2000。
- 连续签到（昨天签过）额外得保底：等级÷2 上下浮动 3。
- 断签时记下欠的天数，可以用补签补回；全部补完后连续天数恢复。
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from ..store.models.game import Checkin, CheckinDaily, Player
from . import core, economy, tuning
from .results import CheckinResult, MakeupResult


def stamina_gain(level: int, count: int) -> int:
    return int(tuning.formula('checkin_stamina', base=tuning.value('stamina_per_checkin'), level=int(level), count=int(count)))


def checkin_pity(level: int) -> int:
    center = int(level) // 2
    return max(0, random.randint(center - 3, center + 3))


def _missed_days(last: date | None, today: date) -> int:
    return 0 if last is None else max(0, (today - last).days - 1)


def _apply_gap(streak: int, owed: int, saved: int, broke: int, extra: int) -> tuple[int, int, int, int]:
    if extra <= 0:
        return streak, owed, saved, broke
    if owed == 0:
        saved, owed, broke = streak, extra, extra
    else:
        owed += extra
        broke += extra
    return 1, owed, saved, broke


async def _bump_daily(day: date) -> int:
    row = await CheckinDaily.get_or_none(day=day)
    if row is None:
        await CheckinDaily.create(day=day, count=1)
        return 1
    row.count += 1
    await row.save(update_fields=["count"])
    return row.count


async def _checkin_row(openid: str) -> Checkin:
    row = await Checkin.get_or_none(player_id=openid)
    return row if row is not None else await Checkin.create(player_id=openid)


async def checkin(openid: str) -> CheckinResult:
    today = core.today()
    yesterday = today - timedelta(days=1)
    year_card = any(kind == "year" for kind, _ in await economy.active_sponsor_cards(openid))
    async with core.tx():
        created = await core._ensure_player(openid)
        state = await _checkin_row(openid)
        user = await Player.get(openid=openid)
        if state.last_date == today:
            return CheckinResult(created=created, already_today=True, rank=0, count=state.count, stamina=user.stamina,
                                 gained=0, streak=state.streak, owed=state.owed)
        last = state.last_date
        streak, owed, saved, broke = state.streak, state.owed, state.saved_streak, state.break_owed
        consecutive = last == yesterday
        if last is None:
            streak = 1
        elif consecutive:
            streak += 1
        else:
            streak, owed, saved, broke = _apply_gap(streak, owed, saved, broke, _missed_days(last, today))
        new_count = state.count + 1
        gained = stamina_gain(user.level, new_count)
        if year_card:     # 年卡：签到基础体力 +10%
            gained = gained * (100 + tuning.value('year_checkin_stamina_pct')) // 100
        gained = max(0, min(tuning.value('stamina_cap') - user.stamina, gained))
        user.stamina += gained
        await user.save(update_fields=["stamina"])
        pity_gained = checkin_pity(user.level) if consecutive else 0
        pity = await core.read_pity(openid)
        if pity_gained:
            pity = await core.write_pity(openid, pity + pity_gained)
        state.count, state.last_date = new_count, today
        state.streak, state.owed, state.saved_streak, state.break_owed = streak, owed, saved, broke
        await state.save()
        rank = await _bump_daily(today)
        return CheckinResult(created=created, already_today=False, rank=rank, count=new_count, stamina=user.stamina,
                             gained=gained, streak=streak, owed=owed, pity_gained=pity_gained, pity=pity)


async def makeup_checkin(openid: str, days: int | None) -> MakeupResult:
    if days is not None and days <= 0:
        return MakeupResult(ok=False, error="bad_qty")
    async with core.tx():
        return await _makeup(openid, days)


async def _makeup(openid: str, days: int | None) -> MakeupResult:
    """补签（不开事务，补签符使用时在道具的事务里调用）。"""
    if days is not None and days <= 0:
        return MakeupResult(ok=False, error="bad_qty")
    today = core.today()
    yesterday = today - timedelta(days=1)
    state = await Checkin.get_or_none(player_id=openid)
    user = await core.get_player(openid)
    if state is None or user is None:
        return MakeupResult(ok=False, error="no_user")
    last_date = state.last_date
    streak, owed, saved, broke = state.streak, state.owed, state.saved_streak, state.break_owed
    extra = _missed_days(last_date, today)
    if extra > 0 and owed == 0:
        streak, owed, saved, broke = _apply_gap(streak, owed, saved, broke, extra)
        if last_date is not None and last_date < yesterday:
            last_date = yesterday
    if owed <= 0:
        return MakeupResult(ok=False, error="no_owed", count=state.count, streak=streak, owed=0,
                            stamina=user.stamina)
    fill = owed if days is None else min(days, owed)
    count = state.count
    gained = 0
    for _ in range(fill):
        count += 1
        gained += stamina_gain(user.level, count)
        owed -= 1
    restored = False
    if owed == 0:
        signed_today = last_date == today
        streak = saved + broke + (1 if signed_today else 0)
        if not signed_today:
            last_date = yesterday
        saved = broke = 0
        restored = True
    gained = max(0, min(tuning.value('stamina_cap') - user.stamina, gained))
    user.stamina += gained
    await user.save(update_fields=["stamina"])
    state.count, state.last_date = count, last_date
    state.streak, state.owed, state.saved_streak, state.break_owed = streak, owed, saved, broke
    await state.save()
    return MakeupResult(ok=True, days=fill, gained=gained, count=count, streak=streak, owed=owed,
                        stamina=user.stamina, restored=restored)
