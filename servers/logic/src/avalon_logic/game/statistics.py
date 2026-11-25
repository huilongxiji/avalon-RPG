"""只读统计查询；收支分别累计，失败和未提交的操作不在这里。"""
from collections import Counter

from avalon_contracts.api.stats import StatsFilter, StatsKind
from avalon_contracts.errors import GameError
from tortoise.functions import Avg, Count, Sum

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


def dates(f: StatsFilter):
    start, end = f.from_date or core.today(), f.to_date or core.today()
    if start > end or (end - start).days > 365:
        raise GameError('invalid', '起止日期需要按先后顺序填写，最多查询 366 天')
    return start, end


def filtered(model, f: StatsFilter):
    start, end = dates(f)
    query = model.filter(day__gte=start, day__lte=end)
    for key in ('openid', 'source', 'currency', 'dungeon_id', 'monster_id', 'item_name'):
        value = getattr(f, key)
        if value not in ('', None) and key in model._meta.fields:
            query = query.filter(**{key: value})
    return query


async def economy_totals(query):
    totals = {}
    for label, sign in (('income', 'gt'), ('expense', 'lt')):
        rows = await query.filter(**{f'delta__{sign}': 0}).annotate(amount=Sum('delta')).group_by('currency').values('currency', 'amount')
        for row in rows:
            entry = totals.setdefault(row['currency'], {'currency': row['currency'], 'income': 0, 'expense': 0})
            entry[label] = abs(row['amount'] or 0)
    return [dict(row, net=row['income'] - row['expense']) for _, row in sorted(totals.items())]


async def query(kind: StatsKind, f: StatsFilter) -> dict:
    start, end = dates(f)
    # 和投递器使用相同的 game → stats 锁顺序；一次页面查询对应完整提交的快照。
    async with core.tx(), transaction('stats'):
        result = {'from': start, 'to': end, 'page': f.page, 'size': f.size}
        if kind == 'overview':
            activity = filtered(DailyActivity, f)
            challenges = await activity.annotate(amount=Sum('challenges')).values('amount')
            first = await StatsEvent.all().order_by('at').first()
            daily = await DailySummary.filter(day__gte=start, day__lte=end).order_by('day').values()
            if f.openid:
                days = await activity.order_by('day').values('day', 'checkin', 'challenges')
                daily = [dict(day=r['day'], active_players=1, checkins=int(r['checkin']),
                              battles=await BattleLog.filter(day=r['day'], openid=f.openid).count(),
                              data={'challenges': r['challenges']}) for r in days]
            result.update(
                players=await Player.all().count(),
                active_players=len(await activity.distinct().values_list('openid', flat=True)),
                checkins=await activity.filter(checkin=True).count(),
                challenges=(challenges[0]['amount'] if challenges else 0) or 0,
                battles=await filtered(BattleLog, f).count(),
                economy=await economy_totals(filtered(EconomyLog, f)),
                pending=await StatsOutbox.all().count(),
                recorded_since=first.at if first else None,
                daily=daily,
            )
            return result
        model = {'economy': EconomyLog, 'battles': BattleLog, 'drops': DropLog, 'effects': BattleLog}[kind]
        rows = filtered(model, f)
        result['total'] = await rows.count()
        if kind == 'effects':
            counts = Counter()
            # 分批读取效果 JSON，避免把全部战报一次装进内存。
            cursor = 0
            while batch := await rows.filter(id__gt=cursor).order_by('id').limit(500).values('id', 'effects'):
                for row in batch:
                    counts.update({k: int(v) for k, v in row['effects'].items()})
                cursor = batch[-1]['id']
            result['items'] = [{'effect': key, 'triggers': value} for key, value in counts.most_common()]
            return result
        result['items'] = await rows.order_by('-at', '-id').offset((f.page - 1) * f.size).limit(f.size).values()
        if kind == 'economy':
            result['totals'] = await economy_totals(rows)
        elif kind == 'battles':
            result['outcomes'] = await rows.annotate(count=Count('id')).group_by('outcome').values('outcome', 'count')
            result['damage'] = await rows.annotate(player=Sum('player_damage'), foe=Sum('foe_damage'), rounds=Avg('rounds')).values('player', 'foe', 'rounds')
        else:
            result['totals'] = await rows.annotate(quantity_sum=Sum('quantity')).group_by('status').values('status', 'quantity_sum')
        return result
