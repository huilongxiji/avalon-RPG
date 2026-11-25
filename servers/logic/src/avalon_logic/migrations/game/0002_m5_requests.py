import functools
from json import dumps, loads

from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('game', '0001_initial')]

    initial = False

    operations = [
        ops.CreateModel(
            name='CommandReceipt',
            fields=[
                ('key', fields.CharField(primary_key=True, unique=True, db_index=True, max_length=64)),
                ('fingerprint', fields.CharField(max_length=64)),
                ('result', fields.JSONField(encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads)),
                ('created_at', fields.DatetimeField(db_index=True, auto_now=False, auto_now_add=True)),
            ],
            options={'table': 'command_receipts', 'app': 'game', 'pk_attr': 'key', 'table_description': '请求重放回执，与游戏修改同事务提交；重复消息不会重复扣费或发奖。'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='GameAudit',
            fields=[
                ('id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('actor', fields.CharField(max_length=64)),
                ('action', fields.CharField(max_length=64)),
                ('detail', fields.JSONField(default=dict, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={'table': 'game_audit', 'app': 'game', 'pk_attr': 'id', 'table_description': '超管游戏操作审计，与存档修改一起提交。'},
            bases=['Model'],
        ),
        ops.AlterModelOptions(
            name='Checkin',
            options={'table': 'checkins', 'app': 'game', 'pk_attr': 'player_id'},
        ),
        ops.AlterModelOptions(
            name='LastChallenge',
            options={'table': 'last_challenges', 'app': 'game', 'pk_attr': 'player_id'},
        ),
        ops.AlterModelOptions(
            name='Pity',
            options={'table': 'pity', 'app': 'game', 'pk_attr': 'player_id', 'table_description': '保底值：全副本共用一个。'},
        ),
        ops.AlterModelOptions(
            name='Wallet',
            options={'table': 'wallets', 'app': 'game', 'pk_attr': 'player_id'},
        ),
    ]
