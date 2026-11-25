"""补齐原版年卡的可配置加成；保留所有已有设定值。"""
from tortoise import migrations
from tortoise.migrations import operations as ops

SETTINGS = [
    ('year_exp_bonus_pct', 5, '年卡经验加成百分比'),
    ('year_coin_bonus_pct', 5, '年卡代币加成百分比'),
    ('year_equipment_drop_pct', 10, '年卡装备掉率加成百分比'),
    ('year_normal_weight_reduction_pct', 10, '年卡普通怪权重降低百分比'),
    ('year_cooldown_reduction_pct', 50, '年卡副本冷却缩短百分比'),
]


async def forward(apps, schema_editor):
    Version = apps.get_model('rules', 'RuleVersion')
    Setting = apps.get_model('rules', 'SettingRow')
    db = schema_editor.client
    for version_id in await Version.all().using_db(db).values_list('id', flat=True):
        for key, value, description in SETTINGS:
            if not await Setting.filter(version_id=version_id, key=key).using_db(db).exists():
                await Setting.create(version_id=version_id, key=key, value=value, description=description, using_db=db)


class Migration(migrations.Migration):
    dependencies = [('rules', '0004_game_parameters')]
    operations = [ops.RunPython(forward, reverse_code=ops.RunPython.noop)]
