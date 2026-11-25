"""统计库 stats.db 的模型：只追加的流水，供数据大屏使用。模拟任务不写这里。"""

from __future__ import annotations

from tortoise import fields
from tortoise.models import Model


class BattleLog(Model):
    id = fields.BigIntField(primary_key=True)
    at = fields.DatetimeField(auto_now_add=True, db_index=True)
    openid = fields.CharField(max_length=64, db_index=True)
    source = fields.CharField(max_length=16)        # dungeon / tower / world_boss
    dungeon_id = fields.IntField(null=True)
    monster_id = fields.CharField(max_length=64)
    rules_version = fields.IntField(null=True)
    won = fields.BooleanField()
    rounds = fields.IntField()
    player_damage = fields.BigIntField(default=0)
    foe_damage = fields.BigIntField(default=0)
    effects = fields.JSONField(default=dict)        # 各效果触发次数
    event_id = fields.CharField(max_length=64, null=True, unique=True)
    operation_id = fields.CharField(max_length=64, default='', db_index=True)
    day = fields.DateField(null=True, db_index=True)
    outcome = fields.CharField(max_length=16, default='loss')

    class Meta:
        table = "battle_log"


class EconomyLog(Model):
    id = fields.BigIntField(primary_key=True)
    at = fields.DatetimeField(auto_now_add=True, db_index=True)
    openid = fields.CharField(max_length=64, db_index=True)
    currency = fields.CharField(max_length=16)      # coins / world_coins / stamina ...
    delta = fields.BigIntField()
    balance = fields.BigIntField()
    source = fields.CharField(max_length=32)        # checkin / dungeon / enhance / market ...
    event_id = fields.CharField(max_length=64, null=True, unique=True)
    operation_id = fields.CharField(max_length=64, default='', db_index=True)
    day = fields.DateField(null=True, db_index=True)
    actor = fields.CharField(max_length=64, default='')
    rules_version = fields.IntField(null=True)
    detail = fields.JSONField(default=dict)

    class Meta:
        table = "economy_log"


class DropLog(Model):
    id = fields.BigIntField(primary_key=True)
    at = fields.DatetimeField(auto_now_add=True, db_index=True)
    openid = fields.CharField(max_length=64, db_index=True)
    source = fields.CharField(max_length=32)
    item_name = fields.CharField(max_length=128)
    quantity = fields.IntField(default=1)
    event_id = fields.CharField(max_length=64, null=True, unique=True)
    operation_id = fields.CharField(max_length=64, default='', db_index=True)
    day = fields.DateField(null=True, db_index=True)
    rules_version = fields.IntField(null=True)
    dungeon_id = fields.IntField(null=True)
    monster_id = fields.CharField(max_length=64, default='')
    status = fields.CharField(max_length=16, default='stored')

    class Meta:
        table = "drop_log"


class DailySummary(Model):
    day = fields.DateField(primary_key=True)
    active_players = fields.IntField(default=0)
    checkins = fields.IntField(default=0)
    battles = fields.IntField(default=0)
    data = fields.JSONField(default=dict)

    class Meta:
        table = "daily_summary"


class StatsEvent(Model):
    """投递回执：同一个 outbox 事件至多计入一次。"""
    id = fields.CharField(max_length=64, primary_key=True)
    at = fields.DatetimeField(db_index=True)
    day = fields.DateField(db_index=True)
    kind = fields.CharField(max_length=16)
    operation_id = fields.CharField(max_length=64, db_index=True)

    class Meta:
        table = 'stats_events'


class DailyActivity(Model):
    id = fields.BigIntField(primary_key=True)
    day = fields.DateField(db_index=True)
    openid = fields.CharField(max_length=64)
    checkin = fields.BooleanField(default=False)
    challenges = fields.IntField(default=0)

    class Meta:
        table = 'daily_activity'
        unique_together = (('day', 'openid'),)
