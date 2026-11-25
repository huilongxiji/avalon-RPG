import functools
from json import dumps, loads

from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('game', '0002_m5_requests')]

    initial = False

    operations = [
        ops.CreateModel(
            name='StatsOutbox',
            fields=[
                ('id', fields.CharField(primary_key=True, unique=True, db_index=True, max_length=64)),
                ('payload', fields.JSONField(encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads)),
                ('created_at', fields.DatetimeField(db_index=True, auto_now=False, auto_now_add=True)),
            ],
            options={'table': 'stats_outbox', 'app': 'game', 'pk_attr': 'id', 'table_description': '与存档修改同事务提交，统计库确认写入后删除；进程重启后可继续投递。'},
            bases=['Model'],
        ),
    ]
