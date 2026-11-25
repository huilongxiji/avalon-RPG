"""旧指令及别名的完整清单和参数解析。只构造接口请求，不读数据库、不计算游戏规则。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from avalon_contracts.api.game import BY_KEY
from avalon_contracts.errors import GameError
from pydantic import ValidationError

SLOTS = {"武器": "weapon", "护甲": "armor", "手镯": "bracelet", "项链": "necklace", "宝石": "gem"}
FEATURES = {"保底": "pity", "减少副本体力消耗": "stamina", "体力": "stamina", "必遇": "boss",
            "掉率": "drop_pct", "装备掉率": "drop_pct", "祝福": "bless", "金币": "coin_pct",
            "副本金币": "coin_pct", "经验": "exp_pct", "副本经验": "exp_pct", "连战": "chain", "探寻": "explore"}


@dataclass(frozen=True)
class Command:
    name: str
    usage: str = ""
    aliases: tuple[str, ...] = ()
    admin: bool = False
    group: str = "其他"


COMMANDS = (
    Command("签到", aliases=("打卡",), group="角色"), Command("面板", group="角色"), Command("个人信息", group="角色"),
    Command("背包", group="背包"), Command("整理背包", group="背包"),
    Command("查看", "<部位>", tuple("查看" + s for s in SLOTS), group="背包"),
    Command("装备详情", "<背包序号>", group="背包"), Command("装备", "<背包序号>", group="背包"),
    Command("卸下", "<部位>", group="背包"),
    Command("强化", "<部位> [目标等级]", tuple("强化" + s for s in SLOTS if s != "宝石"), group="背包"),
    Command("淬炼", "<部位>", tuple("淬炼" + s for s in SLOTS if s != "宝石"), group="背包"),
    Command("出售", "<背包序号> [数量]", group="背包"), Command("批量出售", "<背包序号> <背包序号> ...", group="背包"),
    Command("分解", "<背包序号> [数量]", group="背包"), Command("背包扩容", "<背包序号>", group="背包"),
    Command("合成", "[配方编号]", group="背包"), Command("仓库", group="背包"),
    Command("使用", "<编号> [数量或选择]", group="背包"), Command("道具合成", "[产物名称] [数量]", group="背包"),
    Command("商城", "土罐 [副本编号] [数量] / 世界币 [编号] [数量]", group="交易"),
    Command("兑换", "<兑换码>"), Command("兑换码"),
    Command("副本", "[编号]", group="副本"), Command("副本图鉴", "<编号>", group="副本"),
    Command("战报详情", "[页码]", group="副本"), Command("爬塔", group="副本"),
    Command("爬塔概括", group="副本"), Command("爬塔详情", "[页码]", group="副本"),
    Command("世界BOSS", aliases=("世界boss",), group="副本"), Command("世界排行榜", group="副本"),
    Command("市场", group="交易"), Command("详情", "<挂单编号>", group="交易"),
    Command("上架", "<背包序号> [数量] <单价>", group="交易"), Command("购买", "<挂单编号> [数量]", group="交易"),
    Command("下架", "<挂单编号>", group="交易"), Command("帮助", "[?]", aliases=("菜单", "help")),
    Command("背包菜单"), Command("超管菜单", admin=True),
    Command("给代币", "<目标> <数量或-全部>", admin=True), Command("给世界币", "<目标> <数量或-全部>", admin=True),
    Command("给体力", "<目标> <数量或-全部>", admin=True), Command("给经验", "<目标> <数量或-全部>", admin=True),
    Command("给保底", "<目标> <数量或-全部>", admin=True),
    Command("给爬塔", "<目标> <数量>", ("给爬塔次数",), admin=True),
    Command("给物品", "<目标> <物品名或编号> [数量]", admin=True),
    Command("批量给物品", "<目标> <编号> <编号> ...", admin=True),
    Command("删除物品", "<目标> <名称> [+强化等级] [数量或全部]", ("删物品",), admin=True),
    Command("删除装备", "<目标> <部位>", ("删装备",), admin=True),
    Command("给道具", "<目标> <名称> [数量]", admin=True),
    Command("删除道具", "<目标> <名称> [数量或全部]", ("删道具",), admin=True),
    Command("生成兑换码", "<名称> [数量]", admin=True), Command("补签", "<目标> [天数或全部]", admin=True),
    Command("必遇", "[关闭] <目标>", admin=True), Command("节日福利", "<物品名> <数量> / 关闭", admin=True),
    Command("用户列表", admin=True), Command("给周卡", "<目标>", admin=True),
    Command("给月卡", "<目标>", admin=True), Command("给年卡", "<目标>", admin=True),
    Command("定制宝石", "<目标> <名称> <功能> ...", admin=True), Command("删除定制宝石", "<名称>", admin=True),
)
BY_NAME = {name: command for command in COMMANDS for name in (command.name, *command.aliases)}


@dataclass
class Parsed:
    key: str
    path: dict = field(default_factory=dict)
    body: dict = field(default_factory=dict)
    query: dict = field(default_factory=dict)


def _number(text: str, *, zero: bool = False) -> int:
    if not text.isdigit() or int(text) < (0 if zero else 1):
        raise ValueError("数量必须是正整数")
    return int(text)


def _slot(text: str) -> str:
    value = SLOTS.get(text, text)
    if value not in SLOTS.values():
        raise ValueError("部位不正确")
    return value


def _name_quantity(tokens: list[str], *, removing: bool = False) -> dict:
    if not tokens:
        raise ValueError("缺少名称")
    result = {"quantity": 1}
    if len(tokens) > 1 and removing and tokens[-1] in ("全部", "全"):
        result.update(quantity=None, remove_all=True)
        tokens = tokens[:-1]
    elif len(tokens) > 1 and tokens[-1].isdigit() and not (removing and int(tokens[-1]) == 0):
        result["quantity"] = _number(tokens[-1])
        tokens = tokens[:-1]
    if removing and len(tokens) > 1 and re.fullmatch(r"[+＋]\d+", tokens[-1]):
        result['enhance_level'] = int(tokens.pop()[1:])
    result["name"] = " ".join(tokens)
    return result


def _admin(command: Command, tokens: list[str], mentions: list[str]) -> Parsed:
    name = command.name
    if name == "用户列表":
        if tokens:
            raise ValueError("无需参数")
        return Parsed("admin_users")
    if name == "生成兑换码":
        return Parsed("admin_action", body={"action": "redeem_code", **_name_quantity(tokens)})
    if name == "删除定制宝石":
        if not tokens:
            raise ValueError("缺少名称")
        return Parsed("admin_action", body={"action": "remove_gem", "name": " ".join(tokens)})
    if name == "节日福利":
        if tokens == ["关闭"]:
            return Parsed("admin_action", body={"action": "festival", "enabled": False})
        if len(tokens) < 2:
            raise ValueError("缺少物品和数量")
        return Parsed("admin_action", body={"action": "festival", "name": " ".join(tokens[:-1]), "quantity": _number(tokens[-1])})
    enabled = True
    if name == "必遇" and tokens and tokens[0] == "关闭":
        enabled, tokens = False, tokens[1:]
    targets, all_players = list(mentions), False
    if tokens and tokens[0] in ("全服", "所有人"):
        all_players, tokens = True, tokens[1:]
    elif not targets:
        if not tokens or not re.fullmatch(r"[A-Za-z0-9_-]+", tokens[0]):
            raise ValueError("请指定目标玩家")
        targets.append(tokens.pop(0))
        while tokens and re.fullmatch(r"(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9]+", tokens[0]):
            targets.append(tokens.pop(0))
    result = {"targets": targets, "all_players": all_players}
    resource = {"给代币": "coins", "给世界币": "world_coins", "给体力": "stamina", "给经验": "exp", "给保底": "pity", "给爬塔": "tower"}
    if name in resource:
        if len(tokens) != 1:
            raise ValueError("缺少数量")
        result['action'] = resource[name]
        if tokens[0] in ("-全部", "-全") and name != "给爬塔":
            result['remove_all'] = True
        else:
            negative = tokens[0].startswith('-')
            result['quantity'] = _number(tokens[0][1:] if negative else tokens[0]) * (-1 if negative else 1)
    elif name == "批量给物品":
        result.update(action="items", item_ids=[_number(t, zero=True) for t in tokens])
        if not tokens:
            raise ValueError("缺少物品编号")
    elif name in ("给物品", "删除物品", "给道具", "删除道具"):
        result.update(action={"给物品": "item", "删除物品": "remove_item", "给道具": "prop", "删除道具": "remove_prop"}[name],
                      **_name_quantity(tokens, removing=name.startswith('删除')))
    elif name == "删除装备":
        if len(tokens) != 1:
            raise ValueError("缺少部位")
        result.update(action="destroy_equipped", slot=_slot(tokens[0]))
    elif name == "补签":
        if len(tokens) > 1:
            raise ValueError("参数过多")
        result.update(action="makeup", quantity=None if not tokens or tokens[0] in ("全部", "全") else _number(tokens[0]))
    elif name == "必遇":
        if tokens:
            raise ValueError("参数过多")
        result.update(action="force", enabled=enabled)
    elif name in ("给周卡", "给月卡", "给年卡"):
        if tokens:
            raise ValueError("参数过多")
        result.update(action="card", kind={"给周卡": "week", "给月卡": "month", "给年卡": "year"}[name])
    elif name == "定制宝石":
        features = []
        while tokens and tokens[-1] in FEATURES:
            feature = FEATURES[tokens.pop()]
            if feature in features:
                raise ValueError("功能重复")
            features.append(feature)
        if not tokens or not features:
            raise ValueError("需要名称和功能")
        result.update(action="gem", name=" ".join(tokens), features=features)
    else:
        raise ValueError("未知指令")
    return Parsed("admin_action", body=result)


def parse_command(raw: str, text: str = "", mentions: list[str] | None = None) -> Parsed:
    command = BY_NAME.get(raw)
    if command is None:
        raise GameError("invalid", "没有这个指令")
    name = command.name
    if raw.startswith(name) and raw != name and name in ("查看", "强化", "淬炼"):
        text = raw[len(name):] + " " + text
    tokens = text.strip().split()
    try:
        if name in ('战报详情', '爬塔详情'):
            if len(tokens) > 1 or tokens and not re.fullmatch(r'[0-9]{1,9}', tokens[0]):
                raise ValueError('页码必须是整数')
            return Parsed('battle_detail' if name == '战报详情' else 'tower_detail',
                          query={'page': int(tokens[0])} if tokens else {})
        if name == '爬塔概括':
            if tokens:
                raise ValueError('无需参数')
            return Parsed('tower_summary')
        if name in ("帮助", "背包菜单", "超管菜单", "兑换码"):
            return Parsed({"帮助": "help", "背包菜单": "bag_help", "超管菜单": "admin_help", "兑换码": "redeem_help"}[name])
        if command.admin:
            parsed = _admin(command, tokens, mentions or [])
        else:
            parsed = _player(name, tokens)
        operation = BY_KEY[parsed.key]
        if operation.body:
            parsed.body = operation.body.model_validate(parsed.body).model_dump(mode='json')
        return parsed
    except (ValueError, KeyError, IndexError, ValidationError) as exc:
        raise GameError("invalid", f"用法: {name} {command.usage}".rstrip()) from exc


def _player(name: str, tokens: list[str]) -> Parsed:
    simple = {"签到": "checkin", "面板": "panel", "个人信息": "profile", "背包": "bag", "整理背包": "sort",
              "仓库": "warehouse", "爬塔": "tower", "世界BOSS": "boss", "世界排行榜": "rank", "市场": "market"}
    if name in simple:
        if tokens:
            raise ValueError("无需参数")
        return Parsed(simple[name])
    if name in ("查看", "卸下", "淬炼"):
        if len(tokens) != 1:
            raise ValueError("需要部位")
        slot = _slot(tokens[0])
        return Parsed('equipped', path={'slot': slot}) if name == '查看' else Parsed('unequip' if name == '卸下' else 'temper', body={'slot': slot})
    if name == '强化':
        match = re.fullmatch(r"(武器|护甲|手镯|项链|宝石|weapon|armor|bracelet|necklace|gem)\s*(\d*)", ' '.join(tokens))
        if not match:
            raise ValueError("需要部位")
        return Parsed('enhance', body={'slot': _slot(match[1]), 'target': _number(match[2]) if match[2] else None})
    if name == '批量出售':
        return Parsed('sell_many', body={'indices': [_number(t) for t in tokens]})
    if name in ('装备详情', '装备', '背包扩容', '详情', '下架', '副本图鉴'):
        if len(tokens) != 1:
            raise ValueError("需要编号")
        number = _number(tokens[0])
        key = {'装备详情': 'bag_detail', '装备': 'equip', '背包扩容': 'expand', '详情': 'market_detail', '下架': 'cancel', '副本图鉴': 'dungeon_guide'}[name]
        if name in ('装备', '背包扩容'):
            return Parsed(key, body={'index': number})
        return Parsed(key, path={'index' if name == '装备详情' else 'id': number})
    if name in ('出售', '分解', '购买'):
        if len(tokens) not in (1, 2):
            raise ValueError("需要编号和数量")
        number = _number(tokens[0])
        quantity = _number(tokens[1]) if len(tokens) == 2 else (None if name == '购买' else 1)
        if name == '购买':
            return Parsed('buy', path={'id': number}, body={'quantity': quantity})
        return Parsed('sell' if name == '出售' else 'decompose', body={'index': number, 'quantity': quantity})
    if name == '上架':
        if len(tokens) not in (2, 3):
            raise ValueError("需要编号和价格")
        return Parsed('listing', body={'index': _number(tokens[0]), 'quantity': _number(tokens[1]) if len(tokens) == 3 else 1, 'unit_price': _number(tokens[-1])})
    if name in ('副本', '合成'):
        if len(tokens) > 1:
            raise ValueError("参数过多")
        if not tokens:
            return Parsed('dungeons' if name == '副本' else 'recipes')
        return Parsed('dungeon', path={'id': _number(tokens[0])}) if name == '副本' else Parsed('craft', body={'recipe_id': _number(tokens[0])})
    if name == '商城':
        if not tokens or tokens[0] not in ('土罐', '世界币') or len(tokens) > 3:
            raise ValueError("需要商品类型")
        if len(tokens) == 1:
            return Parsed('shop', query={'kind': 'box' if tokens[0] == '土罐' else 'world'})
        return Parsed('shop_buy', body={'kind': 'box' if tokens[0] == '土罐' else 'world', 'index': _number(tokens[1]),
                                       'quantity': _number(tokens[2]) if len(tokens) == 3 else 1})
    if name == '道具合成':
        return Parsed('prop_craft', body=_name_quantity(tokens)) if tokens else Parsed('prop_recipes')
    if name == '使用':
        if not tokens:
            raise ValueError("缺少道具")
        rest = ' '.join(tokens[1:])
        return Parsed('prop_use', body={'key': tokens[0], 'argument': rest})
    if name == '兑换':
        if len(tokens) != 1 or tokens[0].startswith('兑换码'):
            raise ValueError("缺少兑换码")
        return Parsed('redeem', body={'code': tokens[0]})
    raise ValueError('未知指令')
