"""副本挑战（对应旧版 dungeon 插件的"副本"指令和 db.grant_dungeon_rewards）。

流程：冷却（60 秒，年卡 30 秒）→ 扣体力 → 主战（保底满了、超管指定、定制宝石必遇时必遇 BOSS；
跨界符 / 锁影符 / 引魔符可以指定怪物）→ 胜利结算经验、代币、掉落、保底 → 连战符 / 连战 →
BOSS 战后判定隐秘 → 隐秘战。中途异常或取消时整次挑战回滚。
返回的 DungeonRun 只有数据（打了哪些怪、战斗过程、发了什么），文字由 bot 前端组织。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from typing import Any

from avalon_contracts.rules.monster import DungeonDef, MonsterDef

from ..engine.battle import FighterSpec, build_monster, fight
from . import bag, core, economy, info, panel, props, sponsor, tuning
from .constants import DUNGEON_CHARM_EFFECTS
from .results import DropGrant, DungeonRewardResult

CHALLENGE_COOLDOWN = 60
CHAIN_CHANCE_PCT = 20          # 连战：每次判定的概率
CHAIN_MAX_TRIGGERS = 2         # 每次副本挑战最多连战几次
EXPLORE_CHANCE_PCT = 25        # 探寻：四项各自独立判定
EXPLORE_EXP_PCT = 20
EXPLORE_COIN_PCT = 40

_last_challenge: dict[str, float] = {}


# ---------------------------------------------------------------- 发奖


async def _grant(openid: str, exp: int, coins: int, items: list[tuple[str, int]]) -> DungeonRewardResult:
    player = await core.get_player(openid)
    if player is None:
        return DungeonRewardResult(ok=False, error="no_user")
    level, current_exp, need, gained = await economy._apply_exp(player, exp)
    balance = await economy._add_coins(openid, coins) if coins > 0 else int((await core.wallet(openid)).coins)
    granted: list[DropGrant] = []
    for name, quantity in items:
        added = await bag._add(openid, name, quantity)
        if not added.ok and added.error in ("kinds_full", "stack_full") and (price := info.equipment_price(name)) is not None:
            payout = price * quantity      # 背包放不下的装备自动卖掉
            if payout > 0:
                balance = await economy._add_coins(openid, payout)
            granted.append(DropGrant(name=name, quantity=quantity, ok=True, error="sold", payout=payout))
            continue
        granted.append(DropGrant(name=name, quantity=quantity if added.ok else 0, ok=added.ok, error=added.error,
                                 current=added.current))
    return DungeonRewardResult(ok=True, exp=exp, coins=coins, coin_balance=balance, levels_gained=gained, level=level,
                               current_exp=current_exp, exp_to_next=need, items=tuple(granted))


async def grant_dungeon_rewards(openid: str, exp: int, coins: int, items: list[tuple[str, int]]) -> DungeonRewardResult:
    if exp < 0 or coins < 0:
        return DungeonRewardResult(ok=False, error="bad_qty")
    async with core.tx():
        return await _grant(openid, exp, coins, items)


async def grant_prop_drop(openid: str, name: str, quantity: int) -> DropGrant:
    result = await props.grant_prop(openid, name, quantity)
    return DropGrant(name=name, quantity=quantity if result.ok else 0, ok=result.ok,
                     error=None if result.ok else (result.error or "unknown"))


@core.atomic
async def settle(openid: str, monster: MonsterDef, loot: list[str], prop_names: list[str], gem: Any,
                 exp_bonus: int = 0, coin_bonus: int = 0, festival: bool = True) -> DungeonRewardResult | None:
    """一场胜利的奖励：经验、代币（加成按百分比）、掉落；节日福利每次挑战只在主战、隐秘战各发一次。"""
    items: list[tuple[str, int]] = [(name, 1) for name in loot]
    bonus = info.festival_drop() if festival else None
    fragment = None
    if bonus is not None and bonus[0] == props.FRAGMENT_NAME:
        fragment = bonus
    elif bonus is not None:
        items.append(bonus)
    exp = info.apply_percent(monster.exp, _gem_pct(gem, "exp_pct") + exp_bonus)
    coins = info.apply_percent(monster.coins, _gem_pct(gem, "coin_pct") + coin_bonus)
    grant = await grant_dungeon_rewards(openid, exp, coins, items)
    if not grant.ok:
        return None
    extras: list[DropGrant] = []
    if fragment is not None:
        extras.append(await grant_prop_drop(openid, *fragment))
    for name in prop_names:
        extras.append(await grant_prop_drop(openid, name, 1))
    return replace(grant, items=grant.items + tuple(extras)) if extras else grant


def received_loot(loot: list[str], grant: DungeonRewardResult | None) -> list[str]:
    """真正放进背包（或自动卖掉）的掉落：算保底扣减用。"""
    if grant is None:
        return []
    pending = [item.name for item in grant.items if item.ok]
    kept: list[str] = []
    for name in loot:
        if name in pending:
            pending.remove(name)
            kept.append(name)
    return kept


# ---------------------------------------------------------------- 定制宝石


def _gem_pct(gem: Any, key: str) -> int:
    return int(getattr(gem, key, 0) or 0) if gem is not None else 0


def gem_drop(gem: Any) -> int:
    """宝石的掉率加成（隐秘遇怪和装备掉落都用），老宝石两列取大值。"""
    return max(_gem_pct(gem, "drop_pct"), _gem_pct(gem, "hidden_pct")) if gem is not None else 0


def bless_active(gem: Any, level: int, monster_level: int) -> bool:
    return gem is not None and bool(gem.bless) and level < monster_level


def bless_exp_pct(gem: Any, level: int, monster_level: int) -> int:
    if gem is None or not gem.bless:
        return 0
    dungeons = info.sorted_dungeons()
    return info.bless_exp_pct(dungeons[-1].id if dungeons else 0, level, monster_level)


# ---------------------------------------------------------------- 冷却


async def cooldown_left(openid: str) -> int:
    last = _last_challenge.get(openid)
    if last is None:
        return 0
    cooldown = tuning.value('challenge_cooldown') * (100 - tuning.value('year_cooldown_reduction_pct')) // 100 if await sponsor.year_card_active(openid) else tuning.value('challenge_cooldown')
    remain = cooldown - (core.now() - last)
    if remain <= 0:
        _last_challenge.pop(openid, None)
        return 0
    return int(remain + 0.999)


def occupy(openid: str) -> None:
    previous = _last_challenge.get(openid)
    def undo():
        if previous is None:
            _last_challenge.pop(openid, None)
        else:
            _last_challenge[openid] = previous
    core.on_rollback(undo)
    _last_challenge[openid] = core.now()


def release(openid: str) -> None:
    _last_challenge.pop(openid, None)


# ---------------------------------------------------------------- 挑战


@dataclass
class DungeonRun:
    ok: bool
    error: str | None = None
    dungeon: DungeonDef | None = None
    stamina: int = 0                  # 消耗的体力
    remaining: int = 0                # 剩余体力（不足时是当前体力）
    cooldown_left: int = 0
    pity: int = 0                     # 结束时的保底
    threshold: int = 0                # 必遇 BOSS 需要的保底
    steps: list[dict[str, Any]] = field(default_factory=list)


def _monster_spec(m: MonsterDef) -> FighterSpec:
    return build_monster(core.rules(), m)


@core.atomic
async def challenge(openid: str, dungeon_id: int, forced_monster: MonsterDef | None = None) -> DungeonRun:
    """完整挑战原子提交；任何中途异常或取消都撤销扣费、符咒、奖励和保底。"""
    d = info.dungeon(dungeon_id)
    if d is None:
        return DungeonRun(ok=False, error="no_dungeon")
    if not await economy.user_exists(openid):
        return DungeonRun(ok=False, error="no_user")
    wait = await cooldown_left(openid)
    if wait > 0:
        return DungeonRun(ok=False, error="cooldown", cooldown_left=wait)
    occupy(openid)
    spent, error, remaining = await economy.spend_stamina(openid, d.stamina)
    if not spent:
        release(openid)
        return DungeonRun(ok=False, error=error, remaining=remaining, stamina=d.stamina)
    run = DungeonRun(ok=True, dungeon=d, stamina=d.stamina, remaining=remaining)
    try:
        await _run(openid, d, run, forced_monster)
    except BaseException:
        release(openid)
        raise
    return run


async def _run(openid: str, d: DungeonDef, run: DungeonRun,
               forced_monster: MonsterDef | None) -> None:
    steps = run.steps
    player = await core.get_player(openid)
    if player is None:
        run.ok, run.error = False, "no_user"
        return
    pity = await economy.get_pity(openid)
    pinned = info.boss_hidden_forced(openid)
    gem = await sponsor.equipped_gem(openid)
    gem_pity = gem is not None and bool(gem.pity)
    threshold = info.gem_pity_threshold(d) if gem_pity else info.pity_threshold(d)
    run.threshold = threshold
    forced = pity >= threshold
    gem_boss = await sponsor.note_main_fight(openid)
    year = await sponsor.year_card_active(openid)
    year_drop = tuning.value('year_equipment_drop_pct') if year else 0
    year_exp = tuning.value('year_exp_bonus_pct') if year else 0
    year_coin = tuning.value('year_coin_bonus_pct') if year else 0
    charms = await props.take_prop_buffs(openid, DUNGEON_CHARM_EFFECTS)
    charm_gear = 100 if "dungeon_lucky" in charms else 0
    charm_exp = charms.get("dungeon_exp_bonus", (0, ""))[0]
    charm_coin = charms.get("dungeon_coin_bonus", (0, ""))[0]
    spec = await panel.battle_spec(openid, bless_level=2 if gem is not None and gem.bless else 0,
                                   lifesteal_pct=charms.get("dungeon_lifesteal", (0, ""))[0],
                                   combo_chance=charms.get("dungeon_combo", (0, ""))[0])
    assert spec is not None
    item_exp_pct, item_drop_pct = panel.item_bonuses(await panel.worn_items(openid))
    rules = core.rules()
    rng = core.game_rng()

    monster: MonsterDef | None = None
    note = ""
    if forced_monster is not None:
        monster, note = forced_monster, "cross"            # 跨界符
    if monster is None and "dungeon_repeat" in charms:     # 锁影符：同一副本里重复上次的怪
        last = await props.get_last_challenge(openid)
        if last is not None and last[0] == d.id:
            monster, note = info.monster(last[1]), "repeat"
    if monster is None and "dungeon_lure" in charms:       # 引魔符
        monster, note = info.pick_encounter(d, reduce_normal=year, kind=charms["dungeon_lure"][1]), "lure"
    if monster is None:
        monster = info.pick_boss(d) if forced or pinned or gem_boss else info.pick_encounter(d, reduce_normal=year)
        note = ""
    await props.set_last_challenge(openid, d.id, monster.id)
    first = fight(rules, spec, _monster_spec(monster), rng=rng)
    if forced:
        steps.append({"kind": "pity_forced"})
    elif pinned:
        steps.append({"kind": "pinned"})
    elif gem_boss:
        steps.append({"kind": "gem_boss"})
    if note:
        steps.append({"kind": "charm", "charm": note, "monster": monster.name})
    first_mark = panel.kill_mark_pct(spec, first.foe_stacks, first.won)
    steps.append({"kind": "fight", "role": "main", "monster": monster, "battle": first})
    bless_exp = _bless_step(steps, gem, player.level, monster.level)
    if not first.won:
        run.pity = pity
        return
    loot = info.roll_loot(monster, guarantee_equip=forced, special_bonus=gem_drop(gem),
                          gear_bonus=item_drop_pct + year_drop + charm_gear, mark_bonus=first_mark)
    prop_loot = info.roll_prop_loot(monster)
    explore_exp, explore_coin, explore_pity = await _explore(steps, gem, openid)
    exp_bonus = item_exp_pct + first_mark + year_exp + bless_exp + explore_exp + charm_exp
    coin_bonus = first_mark + year_coin + explore_coin + charm_coin
    grant = await settle(openid, monster, loot, prop_loot, gem, exp_bonus, coin_bonus)
    new_pity = info.next_pity(pity, monster, received_loot(loot, grant), d, forced=forced, gem_pity=gem_pity)
    pity = await economy.adjust_pity(openid, new_pity - pity + explore_pity)
    pity = await _win_bonus(steps, openid, pity)
    steps.append({"kind": "grant", "grant": grant, "exp_pct": _gem_pct(gem, "exp_pct") + exp_bonus,
                  "coin_pct": _gem_pct(gem, "coin_pct") + coin_bonus})

    async def chain_fight(m: MonsterDef, hp: int, carry: dict, role: str) -> tuple[int, dict, bool]:
        """连战 / 连战符的额外战斗：状态保留、不触发开场效果、不耗体力，只结算经验、代币和掉落。"""
        result = fight(rules, spec, _monster_spec(m), rng=rng, hp=hp, carry=carry, entry=False)
        steps.append({"kind": "fight", "role": role, "monster": m, "battle": result})
        if not result.won:
            return result.player_hp, result.carry, False
        mark = panel.kill_mark_pct(spec, result.foe_stacks, result.won)
        fight_loot = info.roll_loot(m, special_bonus=gem_drop(gem), gear_bonus=item_drop_pct + year_drop + charm_gear,
                                    mark_bonus=mark)
        fight_props = info.roll_prop_loot(m)
        e_bonus = item_exp_pct + mark + year_exp + bless_exp + charm_exp
        c_bonus = mark + year_coin + charm_coin
        fight_grant = await settle(openid, m, fight_loot, fight_props, gem, e_bonus, c_bonus, festival=False)
        steps.append({"kind": "grant", "grant": fight_grant, "exp_pct": _gem_pct(gem, "exp_pct") + e_bonus,
                      "coin_pct": _gem_pct(gem, "coin_pct") + c_bonus})
        return result.player_hp, result.carry, True

    async def run_chain(hp: int, carry: dict) -> None:
        """连战：胜利后 20% 概率再打一次主怪，每次挑战最多 2 次，输了就停。"""
        if gem is None or not gem.chain or hp <= 0:
            return
        count = 0
        while count < tuning.value('chain_max_triggers') and random.random() * 100 < tuning.value('chain_chance_pct'):
            count += 1
            hp, carry, won = await chain_fight(monster, hp, carry, "chain")
            if not won:
                return

    chain_hp, chain_carry = first.player_hp, first.carry
    if "dungeon_double" in charms:                       # 连战符：主战胜利后再遇一只随机怪
        extra = info.pick_encounter(d, reduce_normal=year)
        chain_hp, chain_carry, _ = await chain_fight(extra, chain_hp, chain_carry, "double")
    if monster.kind != "boss":
        await run_chain(chain_hp, chain_carry)
        run.pity = pity
        return
    # 隐秘只在 BOSS 主战后判定；连战和隐秘都通过时先打完连战再打隐秘；隐秘战双方回满
    hidden = info.roll_hidden(d, certain=pinned, hidden_bonus=gem_drop(gem))
    await run_chain(chain_hp, chain_carry)
    if hidden is None:
        steps.append({"kind": "hidden_miss"})
        run.pity = pity
        return
    second = fight(rules, spec, _monster_spec(hidden), rng=rng)
    steps.append({"kind": "hidden_appear", "pinned": pinned, "monster": hidden})
    steps.append({"kind": "fight", "role": "hidden", "monster": hidden, "battle": second})
    hidden_bless = _bless_step(steps, gem, player.level, hidden.level)
    if second.won:
        mark = panel.kill_mark_pct(spec, second.foe_stacks, second.won)
        hidden_loot = info.roll_loot(hidden, special_bonus=gem_drop(gem),
                                     gear_bonus=item_drop_pct + year_drop + charm_gear, mark_bonus=mark)
        hidden_props = info.roll_prop_loot(hidden)
        e_bonus = item_exp_pct + mark + year_exp + hidden_bless + charm_exp
        c_bonus = mark + year_coin + charm_coin
        hidden_grant = await settle(openid, hidden, hidden_loot, hidden_props, gem, e_bonus, c_bonus)
        # 隐秘战保底单独结算：击杀 +5；掉了宝石再扣 副本号×25
        gems = [n for n in received_loot(hidden_loot, hidden_grant) if core.item_slot(n) == "gem"]
        if gems:
            steps.append({"kind": "hidden_gem", "cut": d.id * 25})
        pity = await economy.adjust_pity(openid, 5 - d.id * 25 if gems else 5)
        steps.append({"kind": "grant", "grant": hidden_grant, "exp_pct": _gem_pct(gem, "exp_pct") + e_bonus,
                      "coin_pct": _gem_pct(gem, "coin_pct") + c_bonus})
    run.pity = pity


def _bless_step(steps: list[dict[str, Any]], gem: Any, level: int, monster_level: int) -> int:
    exp = bless_exp_pct(gem, level, monster_level)
    if bless_active(gem, level, monster_level) or exp:
        steps.append({"kind": "bless", "active": bless_active(gem, level, monster_level), "exp_pct": exp})
    return exp


async def _explore(steps: list[dict[str, Any]], gem: Any, openid: str) -> tuple[int, int, int]:
    """探寻：胜利后四项各 25% 独立判定（经验 +20%、代币 +40%、体力 +1、保底 +1）。"""
    if gem is None or not gem.explore:
        return 0, 0, 0
    bits: list[str] = []
    exp_bonus = coin_bonus = pity_gain = 0
    if random.random() * 100 < tuning.value('explore_chance_pct'):
        exp_bonus = tuning.value('explore_exp_pct')
        bits.append(f"经验 +{tuning.value('explore_exp_pct')}%")
    if random.random() * 100 < tuning.value('explore_chance_pct'):
        coin_bonus = tuning.value('explore_coin_pct')
        bits.append(f"代币 +{tuning.value('explore_coin_pct')}%")
    if random.random() * 100 < tuning.value('explore_chance_pct'):
        await economy.add_stamina(openid, 1)
        bits.append("体力 +1")
    if random.random() * 100 < tuning.value('explore_chance_pct'):
        pity_gain = 1
        bits.append("保底值 +1")
    if bits:
        steps.append({"kind": "explore", "bits": bits})
    return exp_bonus, coin_bonus, pity_gain


async def _win_bonus(steps: list[dict[str, Any]], openid: str, pity: int) -> int:
    """胜利后：定制宝石的体力、必遇进度。"""
    gain = await sponsor.on_fight_win(openid, True)
    if gain is not None:
        _name, pity_add, stamina_add = gain
        if pity_add:
            pity += pity_add
        if pity_add or stamina_add:
            steps.append({"kind": "gem_gain", "pity": pity_add or 0, "stamina": stamina_add or 0})
    progress = await sponsor.boss_pity_progress(openid)
    if progress is not None:
        steps.append({"kind": "boss_progress", "fights": progress[0], "every": progress[1]})
    return pity


async def cross_challenge(openid: str, monster_name: str) -> DungeonRun:
    """跨界符：使用成功后立即挑战选定的怪物（体力和冷却同副本挑战）。"""
    m = info.find_monster(monster_name)
    player = await core.get_player(openid)
    if m is None or player is None:
        return DungeonRun(ok=False, error="bad_monster" if player else "no_user")
    d = info.cross_dungeon_for(m.id, player.level)
    if d is None:
        return DungeonRun(ok=False, error="locked")
    return await challenge(openid, d.id, m)
