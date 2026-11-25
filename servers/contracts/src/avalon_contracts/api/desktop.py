"""把当前规则库转换为原桌面模拟器可直接消费的数据结构。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from avalon_contracts.rules.formula import FormulaDef

Cell = str | int | float | bool | None


class DesktopCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    source_name: Literal["rules.db"] = "rules.db"
    rules_version: int
    revision: str
    items_rows: list[list[Cell]]
    monster_rows: list[list[Cell]]
    drop_rows: list[list[Cell]] = Field(default_factory=list)
    item_colors: dict[str, str] = Field(default_factory=dict)
    formulas: list[FormulaDef] = Field(default_factory=list)
    rule_data: dict[str, Any] = Field(default_factory=dict)
    drop_rates: dict[str, dict[str, float]] = Field(default_factory=dict)
