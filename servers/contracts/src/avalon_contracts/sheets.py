"""图鉴工作表与列的定义。

一键导出 Excel、本地 Excel 实时数据源、网站的表格视图共用这一份定义，
保证工作表名、列名、列顺序和原来的属性图鉴一致。
"""

from __future__ import annotations

from pydantic import BaseModel


class Column(BaseModel):
    key: str            # 数据字段名
    title: str          # 显示的列名（与原图鉴一致）
    readonly: bool = False   # 只读：由后端生成（计算列、自动生成的说明文字）


class Sheet(BaseModel):
    name: str           # 工作表名（与原图鉴一致）
    table: str          # 对应的数据库表
    columns: list[Column]


def _cols(*items: tuple[str, str] | tuple[str, str, bool]) -> list[Column]:
    return [Column(key=i[0], title=i[1], readonly=(len(i) > 2 and bool(i[2]))) for i in items]


# 原图鉴里就有的工作表
SHEETS: list[Sheet] = [
    Sheet(name="装备信息", table="items", columns=_cols(
        ("id", "编号"), ("name", "名称"), ("slot", "部位"), ("price", "基础价格"),
        ("hp", "生命"), ("atk", "攻击"), ("defense", "防御"), ("agi", "敏捷"), ("mp", "法力"),
        ("special_text", "特殊属性", True), ("set_text", "套装", True),
    )),
    Sheet(name="怪物信息", table="monsters", columns=_cols(
        ("dungeon", "副本序号"), ("no", "编号"), ("name", "名称"), ("kind", "类型"), ("level", "等级"),
        ("coins", "代币"), ("exp", "经验"), ("hp", "生命"), ("atk", "攻击"), ("defense", "防御"),
        ("agi", "敏捷"), ("magic_resist", "法抗"), ("effective_hp", "等效血量", True),
        ("drop1", "掉落物1", True), ("drop2", "掉落物2", True), ("drop3", "掉落物3", True),
    )),
    Sheet(name="掉落表", table="monsters", columns=_cols(
        ("dungeon", "副本序号"), ("no", "编号"), ("name", "名称"), ("weight", "权重"), ("kind", "类型"),
        ("drop1", "掉落物1"), ("rate1", "掉率"), ("drop2", "掉落物2"), ("rate2", "掉率"),
        ("drop3", "掉落物3"), ("rate3", "掉率"), ("drop4", "掉落物4"), ("rate4", "掉率"),
        ("drop5", "掉落物5"), ("rate5", "掉率"), ("drop6", "掉落物6"), ("rate6", "掉率"),
    )),
    Sheet(name="合成配方", table="recipes", columns=_cols(
        ("id", "编号"), ("name", "名称"), ("materials", "材料"),
    )),
    Sheet(name="道具信息", table="props", columns=_cols(
        ("id", "编号"), ("name", "名称"), ("category", "分类"), ("blurb", "效果"), ("value", "价值"),
    )),
    Sheet(name="道具合成配方", table="prop_recipes", columns=_cols(
        ("id", "编号"), ("name", "名称"), ("materials", "材料"),
    )),
]

# 新版本新增、原图鉴没有的工作表
EXTRA_SHEETS: list[Sheet] = [
    Sheet(name="属性定义", table="stat_defs", columns=_cols(
        ("key", "代号"), ("name", "名称"), ("default", "默认值"), ("min", "下限"), ("max", "上限"),
        ("merge", "合并方式"), ("percent", "是否百分比"), ("show", "面板显示"),
    )),
    Sheet(name="层数定义", table="stack_defs", columns=_cols(
        ("key", "代号"), ("name", "名称"), ("owner", "挂在谁身上"), ("max", "上限"),
        ("carry", "跨场保留"), ("boss_immune", "世界BOSS免疫"),
    )),
    Sheet(name="公式", table="formulas", columns=_cols(
        ("name", "公式名"), ("expr", "表达式"), ("description", "说明"),
    )),
    Sheet(name="效果", table="effects", columns=_cols(
        ("id", "代号"), ("name", "名称"), ("desc", "描述", True), ("params", "参数"),
    )),
    Sheet(name="套装", table="item_sets", columns=_cols(
        ("name", "套装名"), ("pieces", "件数"), ("effects", "效果代号"),
    )),
    Sheet(name="副本", table="dungeons", columns=_cols(
        ("id", "编号"), ("name", "名称"), ("stamina", "体力"), ("hidden", "隐秘怪"), ("hidden_rate", "隐秘率"),
    )),
    Sheet(name="设定", table="settings", columns=_cols(
        ("key", "代号"), ("value", "数值"), ("description", "说明"),
    )),
]

ALL_SHEETS: list[Sheet] = SHEETS + EXTRA_SHEETS


def sheet_by_name(name: str) -> Sheet | None:
    for sheet in ALL_SHEETS:
        if sheet.name == name:
            return sheet
    return None
