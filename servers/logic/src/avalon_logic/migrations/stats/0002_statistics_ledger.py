import functools
from json import dumps, loads

from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('stats', '0001_initial')]

    initial = False

    operations = [
        ops.CreateModel(
            name='DailyActivity',
            fields=[
                ('id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('day', fields.DateField(db_index=True)),
                ('openid', fields.CharField(max_length=64)),
                ('checkin', fields.BooleanField(default=False)),
                ('challenges', fields.IntField(default=0)),
            ],
            options={'table': 'daily_activity', 'app': 'stats', 'unique_together': (('day', 'openid'),), 'pk_attr': 'id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='StatsEvent',
            fields=[
                ('id', fields.CharField(primary_key=True, unique=True, db_index=True, max_length=64)),
                ('at', fields.DatetimeField(db_index=True, auto_now=False, auto_now_add=False)),
                ('day', fields.DateField(db_index=True)),
                ('kind', fields.CharField(max_length=16)),
                ('operation_id', fields.CharField(db_index=True, max_length=64)),
            ],
            options={'table': 'stats_events', 'app': 'stats', 'pk_attr': 'id', 'table_description': '投递回执：同一个 outbox 事件至多计入一次。'},
            bases=['Model'],
        ),
        ops.AddField(
            model_name='BattleLog',
            name='day',
            field=fields.DateField(null=True, db_index=True),
        ),
        ops.AddField(
            model_name='BattleLog',
            name='event_id',
            field=fields.CharField(null=True, unique=True, max_length=64),
        ),
        ops.AddField(
            model_name='BattleLog',
            name='operation_id',
            field=fields.CharField(default='', db_index=True, max_length=64),
        ),
        ops.AddField(
            model_name='BattleLog',
            name='outcome',
            field=fields.CharField(default='loss', max_length=16),
        ),
        ops.AddField(
            model_name='DropLog',
            name='day',
            field=fields.DateField(null=True, db_index=True),
        ),
        ops.AddField(
            model_name='DropLog',
            name='dungeon_id',
            field=fields.IntField(null=True),
        ),
        ops.AddField(
            model_name='DropLog',
            name='event_id',
            field=fields.CharField(null=True, unique=True, max_length=64),
        ),
        ops.AddField(
            model_name='DropLog',
            name='monster_id',
            field=fields.CharField(default='', max_length=64),
        ),
        ops.AddField(
            model_name='DropLog',
            name='operation_id',
            field=fields.CharField(default='', db_index=True, max_length=64),
        ),
        ops.AddField(
            model_name='DropLog',
            name='rules_version',
            field=fields.IntField(null=True),
        ),
        ops.AddField(
            model_name='DropLog',
            name='status',
            field=fields.CharField(default='stored', max_length=16),
        ),
        ops.AddField(
            model_name='EconomyLog',
            name='actor',
            field=fields.CharField(default='', max_length=64),
        ),
        ops.AddField(
            model_name='EconomyLog',
            name='day',
            field=fields.DateField(null=True, db_index=True),
        ),
        ops.AddField(
            model_name='EconomyLog',
            name='detail',
            field=fields.JSONField(default=dict, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads),
        ),
        ops.AddField(
            model_name='EconomyLog',
            name='event_id',
            field=fields.CharField(null=True, unique=True, max_length=64),
        ),
        ops.AddField(
            model_name='EconomyLog',
            name='operation_id',
            field=fields.CharField(default='', db_index=True, max_length=64),
        ),
        ops.AddField(
            model_name='EconomyLog',
            name='rules_version',
            field=fields.IntField(null=True),
        ),
    ]
