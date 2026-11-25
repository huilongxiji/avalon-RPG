"""游戏业务的公共部分：事务、时间、规则查询、玩家记录。

- 所有会改数据的操作都包在 ``async with tx():`` 里：先拿进程内的锁（和旧版 db.py 的全局锁一样，
  保证"读-改-写"不会被别的请求插进来），再开 game 库的事务；中途出错整个回滚。
  同一任务内可组合多层 ``tx()``；内部保存点失败会回滚该层，外层失败会回滚整次业务。
- 今天是哪天由 ``today()`` 决定，测试可以用 ``set_clock`` 固定日期。
- 随机数直接用 random 模块（和旧版一致），测试可以 random.seed 固定结果。
- 装备、道具、怪物、副本都来自当前生效的规则（rules.current）。
"""

from __future__ import annotations

import asyncio
import functools
import time
import weakref
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta
from typing import Any

from avalon_contracts.errors import GameError
from avalon_contracts.rules.item import ItemDef
from avalon_contracts.rules.prop import PropDef

from ..engine.ruleset import RuleSet
from ..rules import current
from ..store.models.game import Checkin, Equipped, Pity, Player, Wallet
from ..store.tx import transaction
from .constants import DEFAULT_PLAYER, EQUIP_SLOTS

# ---------------------------------------------------------------- 锁和事务

_locks: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_owner: ContextVar[asyncio.Task | None] = ContextVar("game_transaction_owner", default=None)
_undo: ContextVar[list | None] = ContextVar("game_transaction_undo", default=None)


def on_rollback(callback: Callable[[], None]) -> None:
    """将冷却、运行时开关等内存修改纳入当前事务的回滚。"""
    callbacks = _undo.get()
    if callbacks is not None and _owner.get() is asyncio.current_task():
        callbacks.append(callback)


@asynccontextmanager
async def _savepoint():
    parent = _undo.get()
    callbacks: list = []
    token = _undo.set(callbacks)
    try:
        async with transaction("game"):
            yield
    except BaseException:
        for undo in reversed(callbacks):
            undo()
        raise
    else:
        if parent is not None:
            parent.extend(callbacks)
    finally:
        _undo.reset(token)


@asynccontextmanager
async def tx() -> AsyncIterator[None]:
    """同一任务可以组合业务事务；内层使用保存点，最外层负责排队和提交。

    ContextVar 中记录任务而非布尔值，防止子任务继承上下文后绕过锁。
    不要在事务内创建并等待另一个修改游戏数据的任务。
    """
    task = asyncio.current_task()
    if task is not None and _owner.get() is task:
        async with _savepoint():
            yield
        return
    loop = asyncio.get_running_loop()
    lock = _locks.setdefault(loop, asyncio.Lock())
    async with lock:
        token = _owner.set(task)
        callbacks = _undo.set(None)
        try:
            with current.pinned():
                async with _savepoint():
                    yield
        finally:
            _undo.reset(callbacks)
            _owner.reset(token)


def atomic(fn: Callable[..., Any]) -> Callable[..., Any]:
    """完整玩法的事务边界，包含预检查、扣费、奖励和次数提交。"""
    @functools.wraps(fn)
    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        async with tx():
            return await fn(*args, **kwargs)
    return wrapped


@asynccontextmanager
async def rules_tx():
    """定制宝石的 game/rules 操作：中途异常回滚两个库，成功后才发布规则快照。"""
    from ..rules import editing

    with current.staged():
        try:
            async with tx(), transaction("rules"):
                yield
        except BaseException:
            editing.forget_cache()
            raise


def atomic_rules(fn: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(fn)
    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        async with rules_tx():
            return await fn(*args, **kwargs)
    return wrapped


class Rollback(Exception):
    """在 tx() 里抛出：撤销这次操作已经做的全部改动，并把 result 作为函数的返回值（旧版 conn.rollback() + return）。
    函数要加 @rollback_result 才会把它变成返回值。"""

    def __init__(self, result: object) -> None:
        super().__init__("rollback")
        self.result = result


def rollback_result(fn: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(*args, **kwargs)
        except Rollback as rb:
            return rb.result

    return wrapper


# ---------------------------------------------------------------- 时间

_today: Callable[[], date] = date.today
_now: Callable[[], float] = time.time


def set_clock(today: Callable[[], date] | None = None, now: Callable[[], float] | None = None) -> None:
    """测试用：固定"今天"和"现在"（传 None 恢复真实时间）。"""
    global _today, _now
    _today = today or date.today
    _now = now or time.time


def today() -> date:
    return _today()


def yesterday() -> date:
    return _today() - timedelta(days=1)


def now() -> float:
    return _now()


def local_now() -> datetime:
    return datetime.fromtimestamp(_now())


def game_rng():
    """战斗用的随机数：直接用 random 模块（和旧版一样，整个流程共用一串随机数，测试可以 random.seed 固定）。"""
    import random

    from ..engine.rng import Rng

    rng = Rng.__new__(Rng)
    rng.seed = None  # type: ignore[assignment]
    rng._random = random  # type: ignore[assignment]
    return rng


# ---------------------------------------------------------------- 规则查询


class _Index:
    def __init__(self, rules: RuleSet) -> None:
        self.items_by_name = {i.name: i for i in rules.items.values()}
        self.props_by_name = {p.name: p for p in rules.props.values()}
        self.dungeons_by_name = {d.name: d for d in rules.dungeons.values()}


_cache: dict[int, tuple[Any, Any]] = {}


def per_rules(rules: RuleSet, key: str, build: Callable[[RuleSet], Any]) -> Any:
    """按规则快照缓存算出来的东西（规则换版本后自动重新算）。"""
    slot = _cache.get(id(rules))
    if slot is None or slot[0]() is not rules:
        slot = (weakref.ref(rules), {})
        _cache[id(rules)] = slot
    found = slot[1].get(key)
    if found is None:
        found = slot[1][key] = build(rules)
    return found


def rules() -> RuleSet:
    r = current.get()
    if r is None:
        raise GameError("internal", "规则库里还没有生效的版本")
    return r


def _index(r: RuleSet | None = None) -> _Index:
    return per_rules(r or rules(), "index", _Index)


def item(item_id: int | None) -> ItemDef | None:
    return rules().items.get(item_id) if item_id is not None else None


def item_by_name(name: str) -> ItemDef | None:
    return _index().items_by_name.get((name or "").strip())


def item_name(item_id: int | None) -> str:
    found = item(item_id)
    return found.name if found else ""


def item_slot(name: str) -> str:
    """装备的部位（weapon / armor / bracelet / necklace / gem）；材料和不认识的东西返回空。"""
    found = item_by_name(name)
    if found is None or found.slot not in EQUIP_SLOTS:
        return ""
    return found.slot


def prop(prop_id: int | None) -> PropDef | None:
    return rules().props.get(prop_id) if prop_id is not None else None


def prop_by_name(name: str) -> PropDef | None:
    return _index().props_by_name.get((name or "").strip())


def setting(key: str, default: Any = None) -> Any:
    return rules().setting(key, default)


# ---------------------------------------------------------------- 玩家


async def get_player(openid: str, *, lock: bool = False) -> Player | None:
    q = Player.filter(openid=openid)
    if lock:
        q = q.select_for_update()
    return await q.first()


async def _ensure_player(openid: str) -> bool:
    """没有角色就建一个（默认属性、钱包、签到记录、空装备栏）。返回是否新建。"""
    if await Player.exists(openid=openid):
        return False
    player = await Player.create(openid=openid, **DEFAULT_PLAYER)
    await Wallet.create(player=player)
    await Checkin.create(player=player)
    await Equipped.bulk_create([Equipped(player=player, slot=slot) for slot in EQUIP_SLOTS])
    return True


async def ensure_player(openid: str) -> bool:
    async with tx():
        return await _ensure_player(openid)


async def wallet(openid: str) -> Wallet:
    w = await Wallet.get_or_none(player_id=openid)
    if w is None:
        w = await Wallet.create(player_id=openid)
    return w


async def equipped(openid: str) -> dict[str, Equipped]:
    rows = {e.slot: e for e in await Equipped.filter(player_id=openid)}
    for slot in EQUIP_SLOTS:
        if slot not in rows:
            rows[slot] = await Equipped.create(player_id=openid, slot=slot)
    return rows


async def read_pity(openid: str) -> int:
    row = await Pity.get_or_none(player_id=openid)
    return int(row.value) if row else 0


async def write_pity(openid: str, value: int) -> int:
    stored = max(0, int(value))
    row = await Pity.get_or_none(player_id=openid)
    if row is None:
        await Pity.create(player_id=openid, value=stored)
    else:
        row.value = stored
        await row.save(update_fields=["value"])
    return stored
