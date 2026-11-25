"""全部错误码，以及对应的中文提示。

错误码沿用旧版 ``db.py`` 的写法，bot 前端、网站、模拟器都用这里的中文提示。
业务代码抛出 :class:`GameError`，接口层统一转成 ``ApiResponse.failure``。
"""

from __future__ import annotations

from typing import Any

ERROR_MESSAGES: dict[str, str] = {
    # 通用
    "invalid": "参数不正确",
    "bad_qty": "数量不正确",
    "not_found": "找不到对应的内容",
    "unauthorized": "未登录或令牌无效",
    "forbidden": "没有权限",
    "internal": "服务器内部错误，请稍后再试",
    "logic_unavailable": "逻辑后端暂时无法访问，请稍后再试",
    "rate_limited": "操作太频繁，请稍后再试",
    "conflict": "数据已变化，请重新确认",
    "confirm": "请再次发送相同指令确认",
    "already": "已经装备了相同的物品",
    "bad_cost": "费用不正确",
    "bad_index": "编号不正确",
    "bad_name": "名称不正确",
    "bad_price": "价格必须是正整数",
    "busy": "正在挑战中，请稍后再试",
    "unknown": "找不到对应的道具或兑换码",
    "used": "这个兑换码已经兑换过",
    "short": "持有数量不足",
    "material": "材料不能直接使用",
    "fragment": "碎片不能直接使用，请先合成",
    "need_name": "请填写要选择的装备名称",
    "need_kind": "请选择普通、精英或 BOSS",
    "need_monster": "请填写要挑战的怪物名称",
    "bad_monster": "没有这只怪物",
    "bad_choice": "这不是该礼盒可选择的装备",
    "stamina_full": "体力已满，道具未消耗",
    "level": "等级不足",
    "locked": "副本尚未解锁",
    "low_dungeon": "仅限五本及以上副本的装备淬炼",
    "low_price": "售价低于该装备最低上架价格",
    "no_box": "这个副本没有可购买的礼盒",
    "no_price": "该商品尚未配置价格",
    "no_dungeon": "没有这个副本",
    "no_essence": "没有配置该装备的分解精华",
    "no_gem": "没有所需的宝石",
    "no_gem_config": "该副本没有配置隐秘宝石",
    "no_equip": "没有可用的装备",
    "no_listing": "找不到该市场挂单",
    "no_recipe": "没有这个配方",
    "not_hidden": "只能使用隐秘宝石扩容背包",
    "not_seller": "只能下架自己的商品",
    "own_listing": "不能购买自己上架的商品",
    "personal": "定制宝石不能上架",
    "week_full": "本周上架次数已用完",
    "dup_item": "已经有同名装备",
    "exists": "已经有同名定制宝石",
    # 角色与资源
    "no_user": "你还没有角色，请先签到",
    "no_coins": "代币不足",
    "no_world_coins": "世界币不足",
    "no_stamina": "体力不足",
    "not_enough": "数量不足",
    # 背包与装备
    "no_item": "没有这件物品",
    "bad_slot": "部位不正确",
    "empty": "该部位没有装备",
    "kinds_full": "背包已满",
    "stack_full": "该物品已达堆叠上限",
    "not_enhanceable": "该部位不能强化",
    "not_temperable": "该部位不能淬炼",
    "not_decomposable": "该物品不能分解",
    "capped": "已达上限",
    # 次数与冷却
    "full": "今日次数已用完",
    "cooldown": "冷却中，请稍后再试",
    "already_today": "今天已经签到过了",
    "no_owed": "没有需要补签的天数",
    # 规则
    "rules_invalid": "规则校验未通过",
    "rules_not_draft": "只能修改草稿版本",
    "rules_conflict": "规则版本已变化，请刷新后再试",
    "expr_invalid": "表达式不正确",
    # 模拟
    "sim_busy": "模拟任务排队已满，请稍后再试",
}


def message_of(code: str) -> str:
    """错误码对应的中文提示；未登记的错误码原样返回。"""
    return ERROR_MESSAGES.get(code, code)


class GameError(Exception):
    """业务错误：抛出后由接口层转成统一的失败返回；在事务里抛出会让事务自动回滚。"""

    def __init__(self, code: str, message: str | None = None, **detail: Any) -> None:
        self.code = code
        self.message = message or message_of(code)
        self.detail = detail
        super().__init__(f"{code}: {self.message}")
