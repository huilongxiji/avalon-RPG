"""网站"装备管理"页面用的数据格式（设计文档 10.4 节）。

列表页：按套装分组的装备卡片（ItemGroup → ItemCard），一次取回全部装备；
详情页：一件装备的完整参数、所属套装各档位的效果、效果里的每个公式（原式 + 中文读法）、
        以及它参与的战斗公式（ItemDetail）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..rules.effect import EffectDef
from ..rules.item import ItemDef


class StatValue(BaseModel):
    key: str
    name: str
    value: int | float
    percent: bool = False          # 显示时加 %


class SetRef(BaseModel):
    name: str
    role: str = "main"             # main 主套装 / secondary 副套装


class EffectBrief(BaseModel):
    id: str
    name: str
    desc: str                      # 已经填好参数的中文描述


class TierBrief(BaseModel):
    pieces: int
    effects: list[EffectBrief]


class SetSummary(BaseModel):
    name: str
    tiers: list[TierBrief]
    item_count: int = 0


class ItemCard(BaseModel):
    """卡片上显示的重要参数。"""

    id: int
    name: str
    slot: str
    slot_label: str
    damage_type: str | None = None
    damage_label: str | None = None
    price: int = 0
    main_stats: list[StatValue]            # 生命、攻击、防御、敏捷、法力里不为 0 的
    extra_stats: list[StatValue]           # 其余不为 0 的属性（卡片上最多显示 3 个，其余显示"+N"）
    sets: list[SetRef]
    effect_brief: str = ""                 # 套装/自带效果的一句话摘要
    changed: bool = False                  # 这个草稿里改过（与上一个版本相比）
    added: bool = False                    # 这个草稿里新建的
    retired: bool = False                  # 已下架
    problems: int = 0                      # 校验发现的问题数


class ItemGroup(BaseModel):
    set: SetSummary | None                 # None 表示"未归入套装"
    items: list[ItemCard]


class ItemListResponse(BaseModel):
    version_id: int | None
    groups: list[ItemGroup]
    total: int


class ExprDetail(BaseModel):
    where: str                             # 在效果里的位置，例如"攻击结算后 · 第 2 个动作的数值"
    source: str                            # 原式
    readable: str                          # 中文读法（参数已代入数值）


class EffectDetail(BaseModel):
    id: str
    name: str
    desc: str                              # 填好参数的描述
    template: str                          # 描述模板（编辑用）
    params: dict[str, float]
    logic: list[str]                       # 逐条的中文逻辑说明
    expressions: list[ExprDetail]
    definition: EffectDef                  # 完整数据（效果编辑器用）


class TierDetail(BaseModel):
    pieces: int
    effects: list[EffectDetail]


class SetDetail(BaseModel):
    name: str
    role: str
    tiers: list[TierDetail]
    members: list[str] = Field(default_factory=list)    # 同套装的其他装备


class FormulaRef(BaseModel):
    name: str
    title: str = ""                        # 中文名称，例如"穿透后的有效防御"
    description: str
    expr: str
    readable: str
    variables: dict[str, str]
    required: bool = False                 # 战斗计算要用的内置公式：不能删除、不能改代号和变量
    calls: list[str] = Field(default_factory=list)       # 调用的别的公式
    used_by: list[str] = Field(default_factory=list)     # 被哪些公式调用


class DamageFlow(BaseModel):
    """装备详情"伤害计算"里的一张流程图。"""

    title: str                             # 例如"普通攻击（物理）"
    description: str = ""
    mermaid: str                           # Mermaid 源码，公式方框显示公式的中文名称
    formulas: list[FormulaRef]             # 图里用到的公式（中文名称 + 原式）
    missing: list[str] = Field(default_factory=list)     # 图里用到但规则里没有的公式


class ItemDetail(BaseModel):
    item: ItemDef
    slot_label: str
    stats: list[StatValue]                 # 全部已定义的属性（含 0，编辑表单用）
    sets: list[SetDetail]
    own_effects: list[EffectDetail]        # 装备自带的单件效果
    formulas: list[FormulaRef]             # 这件装备参与的战斗公式
    flows: list[DamageFlow] = Field(default_factory=list)   # 伤害计算流程图
    notes: list[str] = Field(default_factory=list)


class StatInfo(BaseModel):
    key: str
    name: str
    percent: bool = False


class EditMeta(BaseModel):
    """编辑表单用：能选的属性、部位、伤害类型、套装。"""

    version_id: int | None
    stats: list[StatInfo]
    slots: dict[str, str]                  # 部位代号 → 中文
    damage_types: dict[str, str]
    sets: list[str]
