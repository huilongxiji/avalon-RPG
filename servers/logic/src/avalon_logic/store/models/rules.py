"""规则库 rules.db 的模型。

每张规则表都带 version 外键：新建草稿时把父版本的数据整份复制一份（写时复制），
所以每个版本都完整保存在库里，回滚只需重新激活旧版本。
结构化的部分（效果、属性字典、掉落列表）用 JSON 字段，格式由 avalon_contracts.rules 定义并校验。
"""

from __future__ import annotations

from tortoise import fields
from tortoise.models import Model


class RuleVersion(Model):
    id = fields.IntField(primary_key=True)
    parent = fields.ForeignKeyField("rules.RuleVersion", null=True, related_name="children", on_delete=fields.SET_NULL)
    status = fields.CharField(max_length=16, db_index=True)   # draft / active / archived
    note = fields.TextField(default="")
    created_by = fields.CharField(max_length=64, default="")
    created_at = fields.DatetimeField(auto_now_add=True)
    activated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "rule_versions"


class Versioned(Model):
    """所有按版本保存的规则表的公共部分。"""

    id = fields.IntField(primary_key=True)
    version = fields.ForeignKeyField("rules.RuleVersion", related_name=False, on_delete=fields.CASCADE)

    class Meta:
        abstract = True


class StatDefRow(Versioned):
    key = fields.CharField(max_length=64)
    name = fields.CharField(max_length=64)
    default = fields.FloatField(default=0)
    min = fields.FloatField(null=True)
    max = fields.FloatField(null=True)
    merge = fields.CharField(max_length=16, default="sum")
    percent = fields.BooleanField(default=False)
    show = fields.BooleanField(default=True)

    class Meta:
        table = "stat_defs"
        unique_together = (("version", "key"),)


class StackDefRow(Versioned):
    key = fields.CharField(max_length=64)
    name = fields.CharField(max_length=64)
    owner = fields.CharField(max_length=8, default="foe")
    max = fields.IntField(null=True)
    max_stat = fields.CharField(max_length=64, null=True)    # 施加者的这个属性大于 0 时用它当上限
    carry = fields.BooleanField(default=False)
    boss_immune = fields.BooleanField(default=True)

    class Meta:
        table = "stack_defs"
        unique_together = (("version", "key"),)


class FormulaRow(Versioned):
    name = fields.CharField(max_length=64)
    title = fields.CharField(max_length=64, null=True)       # 中文名称（空表示用内置的名称）
    expr = fields.TextField()
    params = fields.JSONField(default=dict)
    description = fields.TextField(default="")

    class Meta:
        table = "formulas"
        unique_together = (("version", "name"),)


class EffectRow(Versioned):
    effect_id = fields.CharField(max_length=64)
    name = fields.CharField(max_length=128)
    data = fields.JSONField()          # 完整的 EffectDef

    class Meta:
        table = "effects"
        unique_together = (("version", "effect_id"),)


class ItemRow(Versioned):
    item_id = fields.IntField()
    name = fields.CharField(max_length=128)
    slot = fields.CharField(max_length=16)
    price = fields.IntField(default=0)
    stats = fields.JSONField(default=dict)
    damage_type = fields.CharField(max_length=16, null=True)
    sets = fields.JSONField(default=list)
    effects = fields.JSONField(default=list)
    sponsor = fields.BooleanField(default=False)             # 赞助宝石
    retired = fields.BooleanField(default=False, db_default=False)   # 已下架（已有的数据库加列时要数据库默认值）

    class Meta:
        table = "items"
        unique_together = (("version", "item_id"), ("version", "name"))


class ItemSetRow(Versioned):
    name = fields.CharField(max_length=128)
    tiers = fields.JSONField()         # [{"pieces": 2, "effects": [...]}, ...]

    class Meta:
        table = "item_sets"
        unique_together = (("version", "name"),)


class MonsterRow(Versioned):
    monster_id = fields.CharField(max_length=64)
    name = fields.CharField(max_length=128)
    kind = fields.CharField(max_length=16, default="normal")
    level = fields.IntField(default=1)
    no = fields.IntField(null=True)
    stats = fields.JSONField(default=dict)
    coins = fields.IntField(default=0)
    exp = fields.IntField(default=0)
    rewards = fields.JSONField(default=list)        # 掉落表：[{"name":..., "chance":...}]
    prop_rewards = fields.JSONField(default=list)
    info_rewards = fields.JSONField(default=list)            # 怪物信息里的归属掉落
    effects = fields.JSONField(default=list)

    class Meta:
        table = "monsters"
        unique_together = (("version", "monster_id"),)


class DungeonRow(Versioned):
    dungeon_id = fields.IntField()
    name = fields.CharField(max_length=128)
    stamina = fields.IntField(default=5)
    hidden_id = fields.CharField(max_length=64, default="")
    hidden_rate = fields.IntField(default=10)
    encounters = fields.JSONField(default=list)     # [{"monster_id":..., "weight":...}]

    class Meta:
        table = "dungeons"
        unique_together = (("version", "dungeon_id"),)


class PropRow(Versioned):
    prop_id = fields.IntField()
    name = fields.CharField(max_length=128)
    category = fields.CharField(max_length=32, default="")
    effect = fields.CharField(max_length=64, default="")
    amount = fields.IntField(default=0)
    blurb = fields.TextField(default="")
    dungeon = fields.CharField(max_length=128, default="")
    value = fields.IntField(default=0)

    class Meta:
        table = "props"
        unique_together = (("version", "prop_id"), ("version", "name"))


class RecipeRow(Versioned):
    recipe_id = fields.IntField()
    output = fields.CharField(max_length=128)
    quantity = fields.IntField(default=1)
    inputs = fields.JSONField()

    class Meta:
        table = "recipes"
        unique_together = (("version", "recipe_id"),)


class PropRecipeRow(Versioned):
    recipe_id = fields.IntField()
    output = fields.CharField(max_length=128)
    quantity = fields.IntField(default=1)
    inputs = fields.JSONField()

    class Meta:
        table = "prop_recipes"
        unique_together = (("version", "recipe_id"),)


class SettingRow(Versioned):
    key = fields.CharField(max_length=64)
    value = fields.JSONField()
    description = fields.TextField(default="")

    class Meta:
        table = "settings"
        unique_together = (("version", "key"),)


class RuleAudit(Model):
    """规则改动审计：只追加，不修改。"""

    id = fields.IntField(primary_key=True)
    version = fields.ForeignKeyField("rules.RuleVersion", null=True, related_name="audits", on_delete=fields.SET_NULL)
    actor = fields.CharField(max_length=64)
    action = fields.CharField(max_length=32)        # create_draft / edit / activate / rollback ...
    target = fields.CharField(max_length=128, default="")
    before = fields.JSONField(null=True)
    after = fields.JSONField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "rule_audit"
