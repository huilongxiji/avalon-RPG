"""存档库 game.db 的模型。

表的内容与旧版 db.py 的表一一对应，便于 M8 阶段迁移旧存档；调整了三处：
1. 装备一律按编号（item_id）存，不再存装备名；
2. 每个部位的强化、淬炼从角色表的宽列拆成 Equipped 表，以后新增部位不用改表结构；
3. 新增 UserBinding，给以后的安卓软件绑定账号用（表先建好，功能以后做）。
旧版用联合主键的表，这里改为自增主键 + 联合唯一约束。
"""

from __future__ import annotations

from tortoise import fields
from tortoise.models import Model

from ..tracked import EconomyTracked


class Player(EconomyTracked, Model):
    openid = fields.CharField(max_length=64, primary_key=True)
    level = fields.IntField(default=1)
    exp = fields.IntField(default=0)
    hp = fields.IntField(default=100)
    atk = fields.IntField(default=10)
    defense = fields.IntField(default=5)
    agi = fields.IntField(default=5)
    mp = fields.IntField(default=10)
    penetration = fields.IntField(default=0)
    stamina = fields.IntField(default=0)
    special_stamina = fields.IntField(default=0)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "players"


class Equipped(Model):
    id = fields.IntField(primary_key=True)
    player = fields.ForeignKeyField("game.Player", related_name="equipped", on_delete=fields.CASCADE)
    slot = fields.CharField(max_length=16)           # weapon / armor / bracelet / necklace / gem
    item_id = fields.IntField(null=True)             # 空表示这个部位没穿
    enhance = fields.IntField(default=0)
    temper = fields.IntField(default=0)

    class Meta:
        table = "equipped"
        unique_together = (("player", "slot"),)


class Wallet(EconomyTracked, Model):
    player = fields.OneToOneField("game.Player", related_name="wallet", primary_key=True, on_delete=fields.CASCADE)
    coins = fields.BigIntField(default=0)
    world_coins = fields.BigIntField(default=0)
    bank = fields.BigIntField(default=0)

    class Meta:
        table = "wallets"


class Checkin(Model):
    player = fields.OneToOneField("game.Player", related_name="checkin", primary_key=True, on_delete=fields.CASCADE)
    count = fields.IntField(default=0)
    last_date = fields.DateField(null=True)
    streak = fields.IntField(default=0)
    owed = fields.IntField(default=0)
    saved_streak = fields.IntField(default=0)
    break_owed = fields.IntField(default=0)

    class Meta:
        table = "checkins"


class CheckinDaily(Model):
    day = fields.DateField(primary_key=True)
    count = fields.IntField(default=0)

    class Meta:
        table = "checkin_daily"


class InventoryItem(Model):
    id = fields.IntField(primary_key=True)
    player = fields.ForeignKeyField("game.Player", related_name="inventory", on_delete=fields.CASCADE)
    item_id = fields.IntField()
    enhance = fields.IntField(default=0)
    temper = fields.IntField(default=0)
    quantity = fields.IntField(default=1)
    acquired_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "inventory"
        unique_together = (("player", "item_id", "enhance", "temper"),)


class WarehouseItem(Model):
    id = fields.IntField(primary_key=True)
    player = fields.ForeignKeyField("game.Player", related_name="warehouse", on_delete=fields.CASCADE)
    prop_id = fields.IntField()
    quantity = fields.IntField(default=1)
    slot = fields.IntField()

    class Meta:
        table = "warehouse"
        unique_together = (("player", "prop_id"),)


class PropBuff(Model):
    """已使用、等待下次强化或副本挑战消耗的符咒。"""

    id = fields.IntField(primary_key=True)
    player = fields.ForeignKeyField("game.Player", related_name="prop_buffs", on_delete=fields.CASCADE)
    effect = fields.CharField(max_length=64)
    amount = fields.IntField(default=0)
    note = fields.CharField(max_length=128, default="")

    class Meta:
        table = "prop_buffs"
        unique_together = (("player", "effect"),)


class LastChallenge(Model):
    player = fields.OneToOneField("game.Player", related_name="last_challenge", primary_key=True, on_delete=fields.CASCADE)
    dungeon_id = fields.IntField()
    monster_id = fields.CharField(max_length=64)

    class Meta:
        table = "last_challenges"


class Pity(EconomyTracked, Model):
    """保底值：全副本共用一个。"""

    player = fields.OneToOneField("game.Player", related_name="pity", primary_key=True, on_delete=fields.CASCADE)
    value = fields.IntField(default=0)

    class Meta:
        table = "pity"


class StatsOutbox(Model):
    """与存档修改同事务提交，统计库确认写入后删除；进程重启后可继续投递。"""
    id = fields.CharField(max_length=64, primary_key=True)
    payload = fields.JSONField()
    created_at = fields.DatetimeField(auto_now_add=True, db_index=True)

    class Meta:
        table = 'stats_outbox'


class TowerDaily(Model):
    id = fields.IntField(primary_key=True)
    player = fields.ForeignKeyField("game.Player", related_name="tower_days", on_delete=fields.CASCADE)
    day = fields.DateField()
    used = fields.IntField(default=0)
    paid = fields.IntField(default=0)
    bonus_free = fields.IntField(default=0)

    class Meta:
        table = "tower_daily"
        unique_together = (("player", "day"),)


class SponsorCard(Model):
    id = fields.IntField(primary_key=True)
    player = fields.ForeignKeyField("game.Player", related_name="sponsor_cards", on_delete=fields.CASCADE)
    kind = fields.CharField(max_length=16)          # week / month / year
    expires_on = fields.DateField()

    class Meta:
        table = "sponsor_cards"
        unique_together = (("player", "kind"),)


class SponsorGem(Model):
    """定制宝石的功能开关与计数。"""

    name = fields.CharField(max_length=128, primary_key=True)
    player = fields.ForeignKeyField("game.Player", related_name="sponsor_gems", on_delete=fields.CASCADE)
    pity = fields.BooleanField(default=False)
    stamina = fields.BooleanField(default=False)
    boss = fields.BooleanField(default=False)
    boss_fights = fields.IntField(default=0)
    hidden_pct = fields.IntField(default=0)
    drop_pct = fields.IntField(default=0)
    coin_pct = fields.IntField(default=0)
    exp_pct = fields.IntField(default=0)
    chain = fields.BooleanField(default=False)
    explore = fields.BooleanField(default=False)
    bless = fields.BooleanField(default=False)

    class Meta:
        table = "sponsor_gems"


class BagExpand(Model):
    id = fields.IntField(primary_key=True)
    player = fields.ForeignKeyField("game.Player", related_name="bag_expands", on_delete=fields.CASCADE)
    gem_name = fields.CharField(max_length=128)

    class Meta:
        table = "bag_expands"
        unique_together = (("player", "gem_name"),)


class WorldBossDaily(Model):
    id = fields.IntField(primary_key=True)
    player = fields.ForeignKeyField("game.Player", related_name="world_boss_days", on_delete=fields.CASCADE)
    day = fields.DateField()
    used = fields.IntField(default=0)
    last_time = fields.BigIntField(default=0)

    class Meta:
        table = "world_boss_daily"
        unique_together = (("player", "day"),)


class WorldBossDamage(Model):
    id = fields.IntField(primary_key=True)
    player = fields.ForeignKeyField("game.Player", related_name="world_boss_damage", on_delete=fields.CASCADE)
    day = fields.DateField(db_index=True)
    damage = fields.BigIntField(default=0)

    class Meta:
        table = "world_boss_damage"
        unique_together = (("player", "day"),)


class WorldBossSettle(Model):
    day = fields.DateField(primary_key=True)
    done = fields.BooleanField(default=False)

    class Meta:
        table = "world_boss_settle"


class MarketListing(Model):
    id = fields.IntField(primary_key=True)
    seller = fields.ForeignKeyField("game.Player", related_name="listings", on_delete=fields.CASCADE)
    item_id = fields.IntField()
    quantity = fields.IntField()
    unit_price = fields.BigIntField()
    enhance = fields.IntField(default=0)
    temper = fields.IntField(default=0)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "market_listings"


class MarketWeekly(Model):
    id = fields.IntField(primary_key=True)
    player = fields.ForeignKeyField("game.Player", related_name="market_weeks", on_delete=fields.CASCADE)
    week = fields.CharField(max_length=16)
    used = fields.IntField(default=0)

    class Meta:
        table = "market_weekly"
        unique_together = (("player", "week"),)


class RedeemCode(Model):
    code = fields.CharField(max_length=64, primary_key=True)
    prop_id = fields.IntField()
    quantity = fields.IntField(default=1)
    used = fields.BooleanField(default=False)

    class Meta:
        table = "redeem_codes"


class EasterRedeem(Model):
    id = fields.IntField(primary_key=True)
    code = fields.CharField(max_length=64)
    player = fields.ForeignKeyField("game.Player", related_name="easter_redeems", on_delete=fields.CASCADE)

    class Meta:
        table = "easter_redeems"
        unique_together = (("code", "player"),)


class Account(Model):
    """账号登记：QQ 用户编号与昵称（角色建立之前就可能有记录，所以不连角色表）。"""

    openid = fields.CharField(max_length=64, primary_key=True)
    user_id = fields.CharField(max_length=64, db_index=True)
    name = fields.CharField(max_length=128, default="")
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "accounts"


class KnownGroup(Model):
    group_id = fields.BigIntField(primary_key=True)

    class Meta:
        table = "known_groups"


class Announcement(Model):
    id = fields.IntField(primary_key=True)
    version = fields.CharField(max_length=32)
    group_id = fields.BigIntField()
    sent_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "announcements"
        unique_together = (("version", "group_id"),)


class UserBinding(Model):
    """预留：以后安卓软件的账号与 QQ 角色绑定。"""

    id = fields.IntField(primary_key=True)
    player = fields.ForeignKeyField("game.Player", related_name="bindings", on_delete=fields.CASCADE)
    platform = fields.CharField(max_length=32)
    account = fields.CharField(max_length=128)

    class Meta:
        table = "user_bindings"
        unique_together = (("platform", "account"),)


class CommandReceipt(Model):
    """请求重放回执，与游戏修改同事务提交；重复消息不会重复扣费或发奖。"""
    key = fields.CharField(max_length=64, primary_key=True)
    fingerprint = fields.CharField(max_length=64)
    result = fields.JSONField()
    created_at = fields.DatetimeField(auto_now_add=True, db_index=True)

    class Meta:
        table = "command_receipts"


class GameAudit(Model):
    """超管游戏操作审计，与存档修改一起提交。"""
    id = fields.BigIntField(primary_key=True)
    actor = fields.CharField(max_length=64)
    action = fields.CharField(max_length=64)
    detail = fields.JSONField(default=dict)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "game_audit"
