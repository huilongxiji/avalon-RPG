from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('rules', '0002_rules_v1_fields')]

    initial = False

    operations = [
        ops.AddField(
            model_name='FormulaRow',
            name='title',
            field=fields.CharField(null=True, max_length=64),
        ),
        ops.AddField(
            model_name='ItemRow',
            name='retired',
            field=fields.BooleanField(default=False, db_default=False),
        ),
    ]
