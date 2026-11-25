"""世界BOSS：每天 5 次、每次冷却 600 秒、每次给 5 普通体力；21:00 前的伤害计入当天排行，
21:00 结算世界币（第 1 名 50、前 3 名 40、前 5 名 35、前 10 名 30、其余参与者 25）。
超管挑战不限次数、没有冷却、不计入排行。（对应旧版 world_boss 插件和 db.py 的世界BOSS部分）"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..engine.battle import BattleResult, build_world_boss, fight
from ..rules import current
from ..store.models.game import Player, WorldBossDaily, WorldBossDamage, WorldBossSettle
from . import core, economy, ledger, panel, tuning
from .results import WorldBossResult, WorldBossStatus


async def world_boss_status(openid: str) -> WorldBossStatus:
    row = await WorldBossDaily.get_or_none(player_id=openid, day=core.today())
    return WorldBossStatus(0, 0) if row is None else WorldBossStatus(row.used, int(row.last_time or 0))


async def world_boss_challenge(openid: str, damage: int, *, superuser: bool = False) -> WorldBossResult:
    """记一次挑战：次数 +1、累计当天伤害、给 5 普通体力。次数和冷却在这里再检查一次。"""
    if not isinstance(damage, int) or damage < 0:
        return WorldBossResult(ok=False, error="bad_qty")
    async with core.tx():
        player = await core.get_player(openid)
        if player is None:
            return WorldBossResult(ok=False, error="no_user")
        day = core.today()
        row = await WorldBossDaily.get_or_none(player_id=openid, day=day)
        now = int(core.now())
        used, last = (row.used, int(row.last_time or 0)) if row else (0, 0)
        if not superuser:
            if row is None:
                row = await WorldBossDaily.create(player_id=openid, day=day, used=0, last_time=0)
            if used >= tuning.value('world_boss_daily_limit'):
                return WorldBossResult(ok=False, error="full", used=used)
            if last and now - last < tuning.value('world_boss_cooldown'):
                return WorldBossResult(ok=False, error="cooldown", used=used,
                                       cooldown_left=tuning.value('world_boss_cooldown') - (now - last))
            row.used += 1
            row.last_time = now
            await row.save(update_fields=["used", "last_time"])
        total = await WorldBossDamage.get_or_none(player_id=openid, day=day)
        if not superuser and core.local_now().hour < tuning.value('world_boss_settle_hour'):
            if total is None:
                total = await WorldBossDamage.create(player_id=openid, day=day, damage=damage)
            else:
                total.damage = int(total.damage) + damage
                await total.save(update_fields=["damage"])
        old = player.stamina
        player.stamina = max(old, min(tuning.value('stamina_cap'), old + tuning.value('world_boss_challenge_stamina')))
        await player.save(update_fields=["stamina"])
        return WorldBossResult(ok=True, used=used + 1 if not superuser else used,
                               total_damage=int(total.damage) if total else 0,
                               stamina_gained=player.stamina - old, stamina=player.stamina)


async def world_boss_rank(day: date | str, limit: int | None = None) -> list[tuple[str, int]]:
    """当天累计伤害排行（降序），最多 limit 名。"""
    day = date.fromisoformat(day) if isinstance(day, str) else day
    limit = tuning.value('world_boss_top_n') if limit is None else limit
    rows = await WorldBossDamage.filter(day=day, damage__gt=0).order_by("-damage", "player_id").limit(limit)
    return [(r.player_id, int(r.damage)) for r in rows]  # type: ignore[attr-defined]


async def world_boss_settle_if_due() -> str | None:
    """结算排名奖励：21:00 后结算当天，21:00 前补结算前一天；已结算过的不重复。返回结算的日期。"""
    async with core.tx():
        # 新项目尚未启用规则时等待初始化，不提前记录结算完成；激活后下一轮继续。
        if current.get() is None:
            return None
        day = core.today() if core.local_now().hour >= tuning.value('world_boss_settle_hour') else core.today() - timedelta(days=1)
        done = await WorldBossSettle.get_or_none(day=day)
        if done is not None and done.done:
            return None
        ranked = await WorldBossDamage.filter(day=day, damage__gt=0).order_by("-damage", "player_id")
        with ledger.operation('world_boss_settle', 'system', 'world_boss_settle:' + day.isoformat()):
            for position, row in enumerate(ranked, start=1):
                owner = row.player_id  # type: ignore[attr-defined]
                if not await Player.exists(openid=owner):
                    continue
                coins = next((c for cap, c in tuning.value('world_boss_reward_tiers') if position <= cap), tuning.value('world_boss_participation_coins'))
                await economy._add_world_coins(owner, coins)
        if done is None:
            await WorldBossSettle.create(day=day, done=True)
        else:
            done.done = True
            await done.save(update_fields=["done"])
    return day.isoformat()


@dataclass(frozen=True)
class WorldBossRun:
    ok: bool
    error: str | None = None
    damage: int = 0
    record: WorldBossResult | None = None
    battle: BattleResult | None = None
    after_settle: bool = False
    superuser: bool = False
    cooldown_left: int = 0


@core.atomic
async def challenge(openid: str, *, superuser: bool = False) -> WorldBossRun:
    """挑战一次世界BOSS（先惰性结算，再检查次数和冷却，打完记录伤害）。"""
    if not await economy.user_exists(openid):
        return WorldBossRun(ok=False, error="no_user")
    await world_boss_settle_if_due()
    if not superuser:
        status = await world_boss_status(openid)
        if status.used >= tuning.value('world_boss_daily_limit'):
            return WorldBossRun(ok=False, error="full")
        if status.last_time:
            wait = tuning.value('world_boss_cooldown') - int(core.now() - status.last_time)
            if wait > 0:
                return WorldBossRun(ok=False, error="cooldown", cooldown_left=wait)
    spec = await panel.battle_spec(openid)
    if spec is None:
        return WorldBossRun(ok=False, error="no_user")
    rules = core.rules()
    result = fight(rules, spec, build_world_boss(rules, spec.level), rng=core.game_rng())
    damage = result.monster_max_hp - result.monster_hp
    record = await world_boss_challenge(openid, damage, superuser=superuser)
    if not record.ok:
        return WorldBossRun(ok=False, error=record.error, cooldown_left=record.cooldown_left, record=record)
    return WorldBossRun(ok=True, damage=damage, record=record, battle=result, superuser=superuser,
                        after_settle=core.local_now().hour >= tuning.value('world_boss_settle_hour'))
