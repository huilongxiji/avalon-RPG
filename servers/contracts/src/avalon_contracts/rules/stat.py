"""属性定义：新增一个属性（比如"吸血率"）只需要加一条定义，不改代码。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# 多件装备 / 多个效果给同一属性加值时怎么合并
MergeMode = Literal["sum", "max", "min", "override"]
MERGE_LABELS = {"sum": "相加", "max": "取最大", "min": "取最小", "override": "覆盖"}


class StatDef(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")   # 代号，表达式里用 self.<key>
    name: str                                         # 中文名
    default: float = 0
    min: float | None = None
    max: float | None = None
    merge: MergeMode = "sum"
    percent: bool = False       # 是否按百分比显示
    show: bool = True           # 是否显示在面板上
