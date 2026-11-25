"""爬塔（对应旧版 tower 插件和 db.py 的爬塔部分）。

从 1 号副本起按顺序连续打（隐秘不参与），击杀后回复已损生命的 20%/30%/50%（普通/精英/首领），
掉率按怪物类型打折；经验、代币按已击杀的最高首领发三倍（没过 1 本首领则按最高怪物发两倍）。
每天 2 次免费，再花 50 体力可以进 1 次（月卡、年卡另送免费次数）。冷却和副本共用。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from avalon_contracts.rules.monster import DungeonDef, MonsterDef

from ..engine.battle import build_monster, fight
from ..store.models.game import TowerDaily
from . import core, dungeon, economy, info, panel, sponsor, tuning
from .results import DungeonRewardResult

HEAL_PERCENT = {"normal": 20, "elite": 30, "boss": 50}
DROP_KEEP = {"normal": 20, "elite": 30, "boss": 50}


async def tower_status(openid: str) -> tuple[str, int, int]:
    """今天能不能爬塔：free / paid / full / no_stamina / no_user，当前体力，今天已用次数。"""
    player = await core.get_player(openid)
    if player is None:
        return "no_user", 0, 0
    stamina = player.stamina + player.special_stamina
    row = await TowerDaily.get_or_none(player_id=openid, day=core.today())
    used, paid, bonus = (row.used, row.paid, row.bonus_free) if row else (0, 0, 0)
    if used >= tuning.value('tower_daily_limit') + bonus:
        return "full", stamina, used
    # 免费次数按"没付费的已用次数"算：付费之后再补发的免费次数，下一次仍然免费
    if used - paid >= tuning.value('tower_free_runs') + bonus:
        return ("no_stamina" if stamina < tuning.value('tower_extra_stamina') else "paid"), stamina, used
    return "free", stamina, used


async def commit_tower_run(openid: str, paid: bool = False) -> None:
    async with core.tx():
        row = await TowerDaily.get_or_none(player_id=openid, day=core.today())
        if row is None:
            await TowerDaily.create(player_id=openid, day=core.today(), used=1, paid=1 if paid else 0, bonus_free=0)
        else:
            row.used += 1
            row.paid += 1 if paid else 0
            await row.save(update_fields=["used", "paid"])


add_tower_free = sponsor.add_tower_free


async def tower_free_bonus(openid: str) -> int:
    row = await TowerDaily.get_or_none(player_id=openid, day=core.today())
    return row.bonus_free if row else 0


def _monster_no(m: MonsterDef) -> int:
    return m.no if m.no is not None else -1


def payout(killed: list[tuple[DungeonDef, MonsterDef]]) -> tuple[int, int]:
    if not killed:
        return 0, 0
    bosses = [(d, m) for d, m in killed if m.kind == "boss"]
    if any(d.id == 1 for d, _ in bosses):
        _, m = max(bosses, key=lambda x: (x[0].id, _monster_no(x[1])))
        return m.exp * 3, m.coins * 3
    _, m = max(killed, key=lambda x: (x[0].id, _monster_no(x[1])))
    return m.exp * 2, m.coins * 2


sorted_encounters = info.sorted_encounters


@dataclass
class TowerRun:
    ok: bool
    error: str | None = None
    status: str = ""
    used: int = 0                    # 今天之前已用次数
    stamina: int = 0                 # 付费进入时：扣完后的剩余体力；体力不够时：当前体力
    paid: bool = False
    outcome: str = ""                # cleared（通关）/ lost（战败）/ empty（没有可挑战的怪物）
    lost_at: DungeonDef | None = None
    fights: list[dict[str, Any]] = field(default_factory=list)   # {"dungeon", "monster", "battle", "heal", "drops"}
    grant: DungeonRewardResult | None = None
    cooldown_left: int = 0


async def _climb(openid: str, run: TowerRun, year: bool, special_bonus: int, spec, item_drop_pct: int):
    rules = core.rules()
    rng = core.game_rng()
    loot: list[str] = []
    prop_loot: list[str] = []
    killed: list[tuple[DungeonDef, MonsterDef]] = []
    mark_exp = mark_coins = 0
    hp: int | None = None
    carry: dict | None = None
    started = False
    for d in info.sorted_dungeons():
        for entry in sorted_encounters(d):
            m = info.monster(entry.monster_id)
            if m is None or m.kind == "hidden":
                continue
            started = True
            # 战斗开始的效果只在每个副本的 BOSS 触发；击杀后临时增益移除，只有 carry 跨战保留
            result = fight(rules, spec, build_monster(rules, m), rng=rng, hp=hp, carry=carry, entry=m.kind == "boss")
            carry = result.carry
            if not result.won:
                run.fights.append({"dungeon": d, "monster": m, "battle": result, "heal": 0, "drops": []})
                run.outcome, run.lost_at = "lost", d
                exp, coins = payout(killed)
                return exp + mark_exp, coins + mark_coins, loot, prop_loot
            heal = (result.player_max_hp - result.player_hp) * tuning.value('heal_percent').get(m.kind, 0) // 100
            hp = result.player_hp + heal
            keep = tuning.value('drop_keep').get(m.kind, 100)
            mark = panel.kill_mark_pct(spec, result.foe_stacks, result.won)
            equip = info.roll_loot(m, keep=keep, special_bonus=special_bonus,
                                   gear_bonus=item_drop_pct + (tuning.value('year_equipment_drop_pct') if year else 0), mark_bonus=mark)
            props_won = info.roll_prop_loot(m, keep=keep)
            loot.extend(equip)
            prop_loot.extend(props_won)
            killed.append((d, m))
            if mark:
                mark_exp += m.exp * mark // 100
                mark_coins += m.coins * mark // 100
            run.fights.append({"dungeon": d, "monster": m, "battle": result, "heal": heal, "drops": equip + props_won})
    exp, coins = payout(killed)
    if not started:
        run.outcome = "empty"
        return 0, 0, loot, prop_loot
    run.outcome = "cleared"
    return exp + mark_exp, coins + mark_coins, loot, prop_loot


@core.atomic
async def climb(openid: str, *, confirmed: bool = True) -> TowerRun:
    """"爬塔"。需要付费进入时，confirmed=False 只返回 status=paid 让玩家确认，不扣体力。"""
    if not await economy.user_exists(openid):
        return TowerRun(ok=False, error="no_user")
    wait = await dungeon.cooldown_left(openid)
    if wait > 0:
        return TowerRun(ok=False, error="cooldown", cooldown_left=wait)
    dungeon.occupy(openid)
    status, stamina, used = await tower_status(openid)
    if status in ("no_user", "full", "no_stamina"):
        dungeon.release(openid)
        return TowerRun(ok=False, error=status, status=status, stamina=stamina, used=used)
    paid = status == "paid"
    if paid and not confirmed:
        dungeon.release(openid)
        return TowerRun(ok=False, error="confirm", status=status, stamina=stamina, used=used, paid=True)
    run = TowerRun(ok=True, status=status, used=used, stamina=stamina, paid=paid)
    if paid:
        spent, error, remaining = await economy.spend_stamina(openid, tuning.value('tower_extra_stamina'))
        if not spent:
            dungeon.release(openid)
            return TowerRun(ok=False, error=error, status=status, stamina=remaining, used=used)
        run.stamina = remaining
    dungeon.occupy(openid)
    try:
        year = await sponsor.year_card_active(openid)
        gem = await sponsor.equipped_gem(openid)
        spec = await panel.battle_spec(openid, bless_level=2 if gem is not None and gem.bless else 0)
        if spec is None:
            raise LookupError("no_user")
        item_drop_pct = panel.item_bonuses(await panel.worn_items(openid))[1]
        exp, coins, loot, prop_loot = await _climb(openid, run, year, dungeon.gem_drop(gem), spec, item_drop_pct)
        if year:                       # 年卡：金币和经验 +5%
            exp = exp * (100 + tuning.value('year_exp_bonus_pct')) // 100
            coins = coins * (100 + tuning.value('year_coin_bonus_pct')) // 100
        grant = await dungeon.grant_dungeon_rewards(openid, exp, coins, [(name, 1) for name in loot])
        if not grant.ok:
            raise LookupError("grant")
        extras = [await dungeon.grant_prop_drop(openid, name, 1) for name in prop_loot]
        run.grant = replace(grant, items=grant.items + tuple(extras)) if extras else grant
        await commit_tower_run(openid, paid)
    except BaseException:
        dungeon.release(openid)
        raise
    return run

