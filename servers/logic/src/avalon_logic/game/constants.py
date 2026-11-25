"""游戏数值常量（和旧版 db.py 一致）。

数值现已存入规则版本并由 tuning 读取。本模块保留旧导入兼容和协议枚举；
运行时数值的默认定义在 rules/game_defaults.py，修改规则后立即生效。
"""

from __future__ import annotations

STAMINA_PER_CHECKIN = 100
STAMINA_CAP = 2000
MAX_ITEM_KINDS = 50
BAG_EXPAND_SLOTS = 2
BAG_EXPAND_COIN = 10000
WEEK_CARD_EXTRA_KINDS = 20
MONTH_CARD_EXTRA_KINDS = 50
YEAR_CARD_EXTRA_KINDS = 9999
YEAR_CHECKIN_STAMINA_PCT = 10
MAX_STACK = 99
MARKET_FEE_PERCENT = 5
MARKET_LIST_LIMIT = 30
MARKET_EXTRA_FEE_PERCENT = 75
MARKET_PRICE_CAP_RATIO = 10
HP_PER_LEVEL = 5
ATK_PER_LEVEL = 1
TOWER_FREE_RUNS = 2
TOWER_EXTRA_STAMINA = 50
TOWER_DAILY_LIMIT = 3
WORLD_SHOP_PRICE = 10                    # 世界币商城单价
WORLD_SHOP_ITEMS = ("强化道具随机礼盒", "副本道具随机礼盒")
# 强化道具随机礼盒：(道具, 权重)，权重合计 100
ENHANCE_BOX_POOL = (
    ("补签符", 16),
    ("世界经验药（小）", 15),
    ("强化祝福符（小）", 9),
    ("强化祝福符（中）", 8),
    ("强化祝福符（大）", 5),
    ("强化保护符（小）", 20),
    ("强化保护符（中）", 13),
    ("强化保护符（大）", 10),
    ("强化奇迹符", 4),
)
# 副本道具随机礼盒：(道具, 权重)，权重合计 100
DUNGEON_BOX_POOL = (
    ("补签符", 16),
    ("世界经验药（小）", 7),
    ("引魔符", 7),
    ("跨界符", 3),
    ("锁影符", 9),
    ("连战符", 7),
    ("幸运符", 5),
    ("泣血符", 13),
    ("连击符", 13),
    ("悟道符", 10),
    ("贪婪符", 10),
)
# 强化符咒：由下一次强化消耗；副本符咒：由下一次副本挑战消耗
ENHANCE_CHARM_EFFECTS = ("enhance_bless", "enhance_protect", "enhance_miracle")
DUNGEON_CHARM_EFFECTS = (
    "dungeon_lure",
    "dungeon_repeat",
    "dungeon_double",
    "dungeon_lucky",
    "dungeon_lifesteal",
    "dungeon_combo",
    "dungeon_exp_bonus",
    "dungeon_coin_bonus",
)
LURE_KINDS = {"普通": "normal", "精英": "elite", "BOSS": "boss"}

WORLD_BOSS_DAILY_LIMIT = 5
WORLD_BOSS_COOLDOWN = 600
WORLD_BOSS_SETTLE_HOUR = 21
WORLD_BOSS_TOP_N = 10
WORLD_BOSS_CHALLENGE_STAMINA = 5         # 每次挑战给予 5 普通体力
# 结算奖励：(名次上限, 世界币)，10 名外参与者 25 世界币
WORLD_BOSS_REWARD_TIERS = ((1, 50), (3, 40), (5, 35), (10, 30))
WORLD_BOSS_PARTICIPATION_COINS = 25

EQUIP_SLOT_LABELS = {"weapon": "武器", "armor": "护甲", "bracelet": "手镯", "necklace": "项链", "gem": "宝石"}
EQUIP_SLOTS = tuple(EQUIP_SLOT_LABELS)
EQUIP_SLOT_KEYS = {label: key for key, label in EQUIP_SLOT_LABELS.items()}
EMPTY_EQUIP = "无"

DEFAULT_PLAYER = {"level": 1, "exp": 0, "hp": 100, "atk": 10, "defense": 5, "agi": 5, "mp": 10,
                  "penetration": 0, "stamina": 0, "special_stamina": 0}
