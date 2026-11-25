"""装备与套装。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Slot = Literal["weapon", "armor", "bracelet", "necklace", "gem", "material"]
SLOT_LABELS = {
    "weapon": "武器",
    "armor": "护甲",
    "bracelet": "手镯",
    "necklace": "项链",
    "gem": "宝石",
    "material": "材料",
}
DamageType = Literal["physical", "magic", "precision"]
DAMAGE_LABELS = {"physical": "物理", "magic": "法术", "precision": "精准"}


class ItemDef(BaseModel):
    id: int = Field(ge=0)                    # 编号跨版本不变，玩家存档只记编号
    name: str
    slot: Slot
    price: int = Field(default=0, ge=0)
    # 基础属性：生命、攻击、防御、敏捷、法力，以及任意已定义的属性
    stats: dict[str, float] = Field(default_factory=dict)
    damage_type: DamageType | None = None    # 只有武器上的才生效
    sets: list[str] = Field(default_factory=list, max_length=2)
    effects: list[str] = Field(default_factory=list)   # 单件被动的效果代号
    sponsor: bool = False                    # 赞助宝石（绑定赞助者，不掉落、不能交易）
    retired: bool = False                    # 已下架：玩家已有的照常使用，但不再掉落、不再出售


class SetTier(BaseModel):
    pieces: int = Field(ge=1, le=6)
    effects: list[str] = Field(min_length=1)


class SetDef(BaseModel):
    name: str
    tiers: list[SetTier] = Field(min_length=1)
