from tortoise import migrations
from tortoise.migrations import operations as ops
import functools
from json import dumps, loads
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('rules', '0001_initial')]

    initial = False

    operations = [
        ops.AddField(
            model_name='ItemRow',
            name='sponsor',
            field=fields.BooleanField(default=False),
        ),
        ops.AddField(
            model_name='MonsterRow',
            name='info_rewards',
            field=fields.JSONField(default=list, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads),
        ),
        ops.AddField(
            model_name='StackDefRow',
            name='max_stat',
            field=fields.CharField(null=True, max_length=64),
        ),
    ]
