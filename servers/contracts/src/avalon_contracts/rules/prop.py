"""道具与配方。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PropDef(BaseModel):
    id: int = Field(ge=0)
    name: str
    category: str = ""
    effect: str = ""            # 道具效果代号（使用后做什么）
    amount: int = 0
    blurb: str = ""             # 说明文字
    dungeon: str = ""
    value: int = 0


class RecipeInput(BaseModel):
    name: str
    quantity: int = Field(default=1, ge=1)


class RecipeDef(BaseModel):
    id: int = Field(ge=0)
    output: str
    quantity: int = Field(default=1, ge=1)
    inputs: list[RecipeInput] = Field(min_length=1)
