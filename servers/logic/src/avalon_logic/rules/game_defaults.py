"""M4 游戏设定与默认公式；持久化到规则版本，旧常量仅保留导入兼容。"""

from __future__ import annotations

import math

from avalon_contracts.rules.formula import FormulaDef
from avalon_contracts.rules.setting import SettingDef

DEFAULTS = {
    "stamina_per_checkin": 100,
    "stamina_cap": 2000,
    "max_item_kinds": 50,
    "bag_expand_slots": 2,
    "bag_expand_coin": 10000,
    "week_card_extra_kinds": 20,
    "month_card_extra_kinds": 50,
    "year_card_extra_kinds": 9999,
    "year_checkin_stamina_pct": 10,
    "year_exp_bonus_pct": 5,
    "year_coin_bonus_pct": 5,
    "year_equipment_drop_pct": 10,
    "year_normal_weight_reduction_pct": 10,
    "year_cooldown_reduction_pct": 50,
    "max_stack": 99,
    "market_fee_percent": 5,
    "market_list_limit": 30,
    "market_extra_fee_percent": 75,
    "market_price_cap_ratio": 10,
    "hp_per_level": 5,
    "atk_per_level": 1,
    "tower_free_runs": 2,
    "tower_extra_stamina": 50,
    "tower_daily_limit": 3,
    "world_shop_price": 10,
    "world_shop_items": ("强化道具随机礼盒", "副本道具随机礼盒"),
    "enhance_box_pool": (
        ("补签符", 16),
        ("世界经验药（小）", 15),
        ("强化祝福符（小）", 9),
        ("强化祝福符（中）", 8),
        ("强化祝福符（大）", 5),
        ("强化保护符（小）", 20),
        ("强化保护符（中）", 13),
        ("强化保护符（大）", 10),
        ("强化奇迹符", 4),
    ),
    "dungeon_box_pool": (
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
    ),
    "world_boss_daily_limit": 5,
    "world_boss_cooldown": 600,
    "world_boss_settle_hour": 21,
    "world_boss_top_n": 10,
    "world_boss_challenge_stamina": 5,
    "world_boss_reward_tiers": ((1, 50), (3, 40), (5, 35), (10, 30)),
    "world_boss_participation_coins": 25,
    "enhance_cost_base": 200,
    "enhance_cost_growth": 1.5,
    "enhance_refund_rate": 75,
    "market_min_percent": 50,
    "temper_base_dungeon": 5,
    "temper_base_level": 10,
    "temper_crafted_bonus": 1,
    "temper_coin_rate": 34,
    "temper_cap_pct": 10,
    "temper_roll_min": 1,
    "temper_roll_max": 5,
    "pity_gain": {"normal": 1, "elite": 2, "boss": 3, "hidden": 5},
    "pity_per_dungeon": 25,
    "pity_gem_per_dungeon": 17,
    "essence_per_box": 3,
    "challenge_cooldown": 60,
    "chain_chance_pct": 20,
    "chain_max_triggers": 2,
    "explore_chance_pct": 25,
    "explore_exp_pct": 20,
    "explore_coin_pct": 40,
    "heal_percent": {"normal": 20, "elite": 30, "boss": 50},
    "drop_keep": {"normal": 20, "elite": 30, "boss": 50},
    "fragment_cost": 9,
    "equip_kind_weights": (("normal", 60), ("elite", 30), ("boss", 10)),
    "boss_every": 8,
    "gem_bonus": {"drop_pct": 50, "coin_pct": 20, "exp_pct": 10},
    "card_days": {"week": 7, "month": 30, "year": 365},
    "card_grant": {"week": (80, 25), "month": (450, 150), "year": (6000, 200)},
    "card_daily": {"week": (15, 0, 0), "month": (20, 5, 1), "year": (30, 15, 2)},
    "easter_codes": ["greendragon666"],
}

LABELS = {
    "stamina_per_checkin": "签到基础体力",
    "stamina_cap": "普通体力上限",
    "max_item_kinds": "基础背包格数",
    "max_stack": "单格堆叠上限",
    "market_fee_percent": "市场上架手续费百分比",
    "challenge_cooldown": "副本冷却秒数",
    "tower_free_runs": "每日免费爬塔次数",
    "tower_extra_stamina": "付费爬塔体力",
    "world_boss_settle_hour": "世界 BOSS 结算小时",
    "world_boss_cooldown": "世界 BOSS 冷却秒数",
    "world_shop_price": "世界币商城单价",
    "easter_codes": "每位玩家限兑一次的彩蛋码",
    "bag_expand_slots": "每次扩容增加格数",
    "bag_expand_coin": "每次扩容代币",
    "week_card_extra_kinds": "周卡额外背包格数",
    "month_card_extra_kinds": "月卡额外背包格数",
    "year_card_extra_kinds": "年卡额外背包格数",
    "year_checkin_stamina_pct": "年卡签到额外体力百分比",
    "year_exp_bonus_pct": "年卡副本与爬塔经验加成百分比",
    "year_coin_bonus_pct": "年卡副本与爬塔代币加成百分比",
    "year_equipment_drop_pct": "年卡装备掉率加成百分比（不含宝石、材料、道具）",
    "year_normal_weight_reduction_pct": "年卡普通怪物权重减少百分比",
    "year_cooldown_reduction_pct": "年卡副本与爬塔冷却减少百分比",
    "market_list_limit": "每周上架数量上限",
    "market_extra_fee_percent": "超额上架额外手续费百分比",
    "market_price_cap_ratio": "市场最高售价倍率",
    "market_min_percent": "市场最低售价百分比",
    "hp_per_level": "每级增加生命",
    "atk_per_level": "每级增加攻击",
    "tower_daily_limit": "每日爬塔次数上限",
    "world_shop_items": "世界币商城商品",
    "enhance_box_pool": "强化礼盒奖池及权重",
    "dungeon_box_pool": "副本礼盒奖池及权重",
    "world_boss_daily_limit": "世界 BOSS 每日次数上限",
    "world_boss_top_n": "世界 BOSS 榜单人数",
    "world_boss_challenge_stamina": "世界 BOSS 挑战体力",
    "world_boss_reward_tiers": "世界 BOSS 排名及世界币奖励",
    "world_boss_participation_coins": "世界 BOSS 参与世界币奖励",
    "enhance_cost_base": "强化基础费用",
    "enhance_cost_growth": "强化费用增长倍率",
    "enhance_refund_rate": "强化退款百分比",
    "temper_base_dungeon": "淬炼副本基数",
    "temper_base_level": "淬炼等级基数",
    "temper_crafted_bonus": "合成装备淬炼加成",
    "temper_coin_rate": "淬炼代币倍率",
    "temper_cap_pct": "淬炼上限百分比",
    "temper_roll_min": "单次淬炼最小增长",
    "temper_roll_max": "单次淬炼最大增长",
    "pity_gain": "各类怪物保底增长",
    "pity_per_dungeon": "每副本装备保底系数",
    "pity_gem_per_dungeon": "每副本宝石保底系数",
    "essence_per_box": "兑换礼盒所需精华",
    "chain_chance_pct": "连战触发百分比",
    "chain_max_triggers": "连战触发次数上限",
    "explore_chance_pct": "探索触发百分比",
    "explore_exp_pct": "探索经验奖励百分比",
    "explore_coin_pct": "探索代币奖励百分比",
    "heal_percent": "各类怪物战后恢复百分比",
    "drop_keep": "各类怪物装备掉落保留百分比",
    "fragment_cost": "合成礼盒碎片数量",
    "equip_kind_weights": "礼盒装备类型及权重",
    "boss_every": "赞助宝石必遇首领间隔",
    "gem_bonus": "赞助宝石掉落代币经验加成百分比",
    "card_days": "各类赞助卡有效天数",
    "card_grant": "各类赞助卡即时奖励",
    "card_daily": "各类赞助卡每日奖励",
}

SETTINGS = [
    SettingDef(key=key, value=value, description=LABELS.get(key, key))
    for key, value in DEFAULTS.items()
]


def _f(name, title, expr, **params):
    return FormulaDef(name=name, title=title, expr=expr, params=params, description=title)


FORMULAS = [
    _f(
        "enhance_step_cost",
        "强化单级费用",
        "floor(base * growth ** level + 0.5)",
        level="当前强化等级",
        base="基础费用",
        growth="费用增长倍率",
    ),
    _f(
        "enhance_success",
        "强化成功率",
        "1 if level < 10 else 0.5 + 0.45 * exp(-0.15 * (level - 10))",
        level="当前强化等级",
    ),
    _f("enhance_stat_mult", "强化属性倍率", "1.10 ** level", level="强化等级"),
    _f(
        "checkin_stamina",
        "签到体力",
        "base + level + count",
        base="基础体力",
        level="玩家等级",
        count="累计签到次数",
    ),
    _f(
        "exp_to_next",
        "升级所需经验",
        "95 * level + level * (level + 4) if level < 20 else floor(previous * 1.2 + 0.5)",
        level="当前等级",
        previous="上一级所需经验（逐级取整）",
    ),
    _f(
        "pity_threshold",
        "副本保底阈值",
        "dungeon_id * per_dungeon",
        dungeon_id="副本编号",
        per_dungeon="每本所需保底",
    ),
    _f(
        "market_fee",
        "市场手续费",
        "gross * percent // 100",
        gross="成交总价",
        percent="手续费百分比",
    ),
]


def validate_settings(settings: dict) -> list[str]:
    problems = []

    def same_shape(value, default):
        if isinstance(default, bool):
            return isinstance(value, bool)
        if isinstance(default, (int, float)):
            return (
                type(value) in ((int,) if isinstance(default, int) else (int, float))
                and 0 <= value <= 1e12
                and math.isfinite(value)
            )
        if isinstance(default, str):
            return isinstance(value, str) and bool(value.strip())
        if isinstance(default, dict):
            return (
                isinstance(value, dict)
                and value.keys() == default.keys()
                and all(same_shape(value[k], v) for k, v in default.items())
            )
        if isinstance(default, (list, tuple)):
            return (
                isinstance(value, (list, tuple))
                and len(value) == len(default)
                and all(same_shape(v, d) for v, d in zip(value, default, strict=True))
            )
        return False

    for key, default in DEFAULTS.items():
        if key not in settings:
            continue
        data = settings[key]
        if key == "easter_codes":
            valid = isinstance(data, list) and all(
                isinstance(v, str) and 0 < len(v) <= 64 for v in data
            )
        else:
            valid = same_shape(data, default)
        if not valid:
            problems.append(f"设定 {key} 的类型、结构或数值范围不正确")
            continue
        if isinstance(default, (int, float)):
            if key.endswith(("percent", "_pct", "_rate")) and data > 100:
                problems.append(f"设定 {key} 不能超过 100%")
            if (
                key
                in (
                    "max_stack",
                    "max_item_kinds",
                    "boss_every",
                    "world_boss_top_n",
                    "enhance_cost_growth",
                    "enhance_cost_base",
                    "temper_coin_rate",
                    "temper_base_level",
                    "temper_roll_min",
                    "fragment_cost",
                    "essence_per_box",
                    "pity_per_dungeon",
                    "pity_gem_per_dungeon",
                )
                and data <= 0
            ):
                problems.append(f"设定 {key} 必须大于 0")
            if key == "world_boss_settle_hour" and data > 23:
                problems.append("结算小时必须在 0～23 之间")
        if key in ("heal_percent", "drop_keep") and any(v > 100 for v in data.values()):
            problems.append(f"设定 {key} 的百分比不能超过 100%")
        if key in ("enhance_box_pool", "dungeon_box_pool", "equip_kind_weights"):
            if sum(v[1] for v in data) <= 0:
                problems.append(f"设定 {key} 的总权重必须大于 0")
            if [v[0] for v in data] != [v[0] for v in default]:
                problems.append(f"设定 {key} 只能修改权重，不能更改奖池物品或类型")
        if key == "world_shop_items" and list(data) != list(default):
            problems.append("商城设定只能使用已支持的商品")
        if key == "world_boss_reward_tiers":
            ranks = [v[0] for v in data]
            if ranks != sorted(set(ranks)) or ranks[0] <= 0:
                problems.append("世界 BOSS 奖励名次必须大于 0 且严格递增")
    merged = {**DEFAULTS, **settings}
    for low, high in [
        ("temper_roll_min", "temper_roll_max"),
        ("tower_free_runs", "tower_daily_limit"),
    ]:
        if (
            isinstance(merged[low], (int, float))
            and isinstance(merged[high], (int, float))
            and merged[low] > merged[high]
        ):
            problems.append(f"设定 {low} 不能大于 {high}")
    return problems


def validate_formulas(formulas, settings: dict) -> list[str]:
    """检查调用签名与边界样例；运行期仍会拒绝越界结果并回滚业务。"""
    from ..engine.expr import ExprRuntimeError

    problems = []
    defaults = {**DEFAULTS, **settings}
    for definition in FORMULAS:
        formula = formulas.get(definition.name)
        if formula is None:
            continue  # 缺失由规则编译器统一报错
        if tuple(formula.params) != tuple(definition.params):
            problems.append(f"公式 {definition.name} 的变量必须为：{'、'.join(definition.params)}")
            continue
        previous = 0
        for level in (0, 1, 9, 10, 19, 20, 50):
            values = dict(level=max(1, level) if definition.name == "exp_to_next" else level,
                          base=defaults['enhance_cost_base'] if definition.name == "enhance_step_cost" else defaults['stamina_per_checkin'],
                          growth=defaults['enhance_cost_growth'], count=level, previous=previous,
                          dungeon_id=max(1, level), per_dungeon=defaults['pity_per_dungeon'],
                          gross=level * 100, percent=defaults['market_fee_percent'])
            try:
                result = formula(**{k: values[k] for k in definition.params})
                if result < 0 or (definition.name in ('exp_to_next', 'pity_threshold', 'enhance_step_cost') and result < 1):
                    raise ValueError('结果必须为非负数，经验、保底阈值和强化费用至少为 1')
                if definition.name == 'enhance_success' and result > 1:
                    raise ValueError('成功率必须在 0～1 之间')
                if definition.name == 'market_fee' and result > values['gross']:
                    raise ValueError('手续费不能超过成交总价')
                previous = result
            except (ExprRuntimeError, ArithmeticError, ValueError) as exc:
                problems.append(f"公式 {definition.name} 边界自检失败：{exc}")
                break
    return problems
