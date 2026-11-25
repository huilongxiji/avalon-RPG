from tortoise import migrations
from tortoise.migrations import operations as ops
import functools
from json import dumps, loads
from tortoise import fields

class Migration(migrations.Migration):
    initial = True

    operations = [
        ops.CreateModel(
            name='BattleLog',
            fields=[
                ('id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('at', fields.DatetimeField(db_index=True, auto_now=False, auto_now_add=True)),
                ('openid', fields.CharField(db_index=True, max_length=64)),
                ('source', fields.CharField(max_length=16)),
                ('dungeon_id', fields.IntField(null=True)),
                ('monster_id', fields.CharField(max_length=64)),
                ('rules_version', fields.IntField(null=True)),
                ('won', fields.BooleanField()),
                ('rounds', fields.IntField()),
                ('player_damage', fields.BigIntField(default=0)),
                ('foe_damage', fields.BigIntField(default=0)),
                ('effects', fields.JSONField(default=dict, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads)),
            ],
            options={'table': 'battle_log', 'app': 'stats', 'pk_attr': 'id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='DailySummary',
            fields=[
                ('day', fields.DateField(primary_key=True, unique=True, db_index=True)),
                ('active_players', fields.IntField(default=0)),
                ('checkins', fields.IntField(default=0)),
                ('battles', fields.IntField(default=0)),
                ('data', fields.JSONField(default=dict, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads)),
            ],
            options={'table': 'daily_summary', 'app': 'stats', 'pk_attr': 'day'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='DropLog',
            fields=[
                ('id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('at', fields.DatetimeField(db_index=True, auto_now=False, auto_now_add=True)),
                ('openid', fields.CharField(db_index=True, max_length=64)),
                ('source', fields.CharField(max_length=32)),
                ('item_name', fields.CharField(max_length=128)),
                ('quantity', fields.IntField(default=1)),
            ],
            options={'table': 'drop_log', 'app': 'stats', 'pk_attr': 'id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='EconomyLog',
            fields=[
                ('id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('at', fields.DatetimeField(db_index=True, auto_now=False, auto_now_add=True)),
                ('openid', fields.CharField(db_index=True, max_length=64)),
                ('currency', fields.CharField(max_length=16)),
                ('delta', fields.BigIntField()),
                ('balance', fields.BigIntField()),
                ('source', fields.CharField(max_length=32)),
            ],
            options={'table': 'economy_log', 'app': 'stats', 'pk_attr': 'id'},
            bases=['Model'],
        ),
    ]
