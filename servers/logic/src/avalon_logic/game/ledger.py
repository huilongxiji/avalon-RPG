"""可靠统计流水：game outbox 原子记账 → stats 幂等投递。

真实 HTTP 写操作和定时世界 BOSS 结算显式开启上下文；模拟器和迁移不写流水。
统计库故障不会回滚已经成功的游戏操作，待投递行保留到下一次重试。
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime, timezone
from uuid import uuid4

from tortoise.functions import Sum

from ..store.models.game import Player, StatsOutbox
from ..store.models.stats import (
    BattleLog,
    DailyActivity,
    DailySummary,
    DropLog,
    EconomyLog,
    StatsEvent,
)
from ..store.tx import transaction
from . import core

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Operation:
    source: str
    actor: str
    operation_id: str
    rules_version: int | None
    task: asyncio.Task | None


_context: ContextVar[Operation | None] = ContextVar('stats_operation', default=None)


def current() -> Operation | None:
    value = _context.get()
    return value if value and value.task is asyncio.current_task() else None


@contextmanager
def operation(source: str, actor: str, operation_id: str = ''):
    token = _context.set(Operation(source, actor, operation_id or uuid4().hex, core.rules().version_id, asyncio.current_task()))
    try:
        yield
    finally:
        _context.reset(token)


async def emit(kind: str, openid: str, **data) -> None:
    context = current()
    if context is None:
        return
    identity = uuid4().hex
    payload = {'id': identity, 'kind': kind, 'source': context.source, 'actor': context.actor,
               'operation_id': context.operation_id, 'rules_version': context.rules_version,
               'openid': openid, 'at': datetime.fromtimestamp(core.now(), timezone.utc).isoformat(),
               'day': core.today().isoformat(), 'data': data}
    await StatsOutbox.create(id=identity, payload=payload)


async def _fight(owner: str, monster: dict, battle: dict, dungeon_id: int | None):
    turns = battle.get('turns', [])
    await emit('battle', owner, dungeon_id=dungeon_id, monster_id=str(monster.get('id', 'world_boss')),
               won=battle['won'], rounds=battle['rounds'],
               outcome='win' if battle['won'] else 'draw' if battle.get('draw') else 'timeout' if battle.get('timeout') else 'loss',
               player_damage=sum(max(0, t.get('total', t.get('damage', 0))) for t in turns if t['side'] == 'player'),
               foe_damage=sum(max(0, t.get('total', t.get('damage', 0))) for t in turns if t['side'] != 'player'),
               effects=battle.get('triggered', {}))


async def _drop(owner: str, row: dict, dungeon_id: int | None, monster_id: str):
    if row.get('ok') and row.get('quantity', 0) > 0:
        await emit('drop', owner, item_name=row['name'], quantity=row['quantity'], dungeon_id=dungeon_id,
                   monster_id=str(monster_id), status='sold' if row.get('error') == 'sold' else 'stored')


async def completed(key: str, owner: str, data: dict) -> None:
    if current() is None:
        return
    run = data.get('battle') if key == 'prop_use' else data
    challenge = key in ('dungeon', 'tower', 'boss') or key == 'prop_use' and bool(run)
    if await Player.exists(openid=owner):
        await emit('activity', owner, checkin=key == 'checkin' and not data.get('already_today'), challenge=bool(challenge))
    if not challenge:
        return
    if key == 'boss':
        await _fight(owner, {'id': 'world_boss'}, data['battle'], None)
    elif key == 'tower':
        awards = defaultdict(deque)
        for item in (data.get('grant') or {}).get('items', []):
            # 爬塔先汇总装备再汇总道具；按名称匹配实际入包/自动出售的结果。
            awards[item['name']].append(item)
        for fight in data['fights']:
            d, m = fight['dungeon']['id'], fight['monster']
            await _fight(owner, m, fight['battle'], d)
            for name in fight['drops']:
                if awards[name]:
                    await _drop(owner, awards[name].popleft(), d, m['id'])
    else:
        monster = ''
        dungeon_id = run['dungeon']['id']
        for step in run.get('steps', []):
            if step.get('battle'):
                monster = step['monster']['id']
                await _fight(owner, step['monster'], step['battle'], dungeon_id)
            for row in (step.get('grant') or {}).get('items', []):
                await _drop(owner, row, dungeon_id, monster)


async def _deliver(payload: dict) -> bool:
    identity = payload['id']
    if await StatsEvent.filter(id=identity).exists():
        return False
    at = datetime.fromisoformat(payload['at'])
    day = date.fromisoformat(payload['day'])
    await StatsEvent.create(id=identity, at=at, day=day, kind=payload['kind'], operation_id=payload['operation_id'])
    common = {'event_id': identity, 'at': at, 'day': day, 'openid': payload['openid'],
              'operation_id': payload['operation_id'], 'source': payload['source'], 'rules_version': payload['rules_version']}
    data = payload['data']
    if payload['kind'] == 'economy':
        await EconomyLog.create(**common, actor=payload['actor'], **data)
    elif payload['kind'] == 'battle':
        await BattleLog.create(**common, **data)
    elif payload['kind'] == 'drop':
        await DropLog.create(**common, **data)
    elif payload['kind'] == 'activity':
        row, _ = await DailyActivity.get_or_create(day=day, openid=payload['openid'])
        row.checkin = row.checkin or data['checkin']
        row.challenges += int(data['challenge'])
        await row.save(update_fields=['checkin', 'challenges'])
    else:
        raise ValueError('未知的统计流水类型')
    return True


async def flush(limit: int = 200) -> int:
    # 必须取得 game 事务锁再读 outbox，不能看到另一任务尚未提交的行。
    async with core.tx():
        rows = await StatsOutbox.all().order_by('created_at', 'id').limit(limit)
        if not rows:
            return 0
        async with transaction('stats'):
            days = set()
            for row in rows:
                if await _deliver(row.payload):
                    days.add(date.fromisoformat(row.payload['day']))
            for day in days:
                total = await DailyActivity.filter(day=day).annotate(total=Sum('challenges')).values('total')
                await DailySummary.update_or_create(day=day, defaults={
                    'active_players': await DailyActivity.filter(day=day).count(),
                    'checkins': await DailyActivity.filter(day=day, checkin=True).count(),
                    'battles': await BattleLog.filter(day=day).count(),
                    'data': {'challenges': (total[0]['total'] if total else 0) or 0}})
        # stats 已提交而这一步失败时，下次通过 StatsEvent 去重后重新确认。
        await StatsOutbox.filter(id__in=[r.id for r in rows]).delete()
        return len(rows)


async def delivery_loop(interval: float = 1):
    while True:
        try:
            delivered = await flush()
        except Exception:
            log.exception('统计流水投递失败，待投递事件已保留')
            delivered = 0
        await asyncio.sleep(0 if delivered == 200 else interval)
