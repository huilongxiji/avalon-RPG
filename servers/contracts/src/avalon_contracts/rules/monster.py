"""怪物、副本、掉落。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MonsterKind = Literal["normal", "elite", "boss", "hidden"]
KIND_LABELS = {"normal": "普通", "elite": "精英", "boss": "BOSS", "hidden": "隐秘"}


class Reward(BaseModel):
    name: str
    chance: float = Field(ge=0, le=100)      # 百分数，如 15 表示 15%


class MonsterDef(BaseModel):
    id: str
    name: str
    kind: MonsterKind = "normal"
    level: int = Field(default=1, ge=1)
    no: int | None = None                    # 图鉴里的编号
    stats: dict[str, float] = Field(default_factory=dict)   # 生命、攻击、防御、敏捷、法抗……
    coins: int = 0
    exp: int = 0
    rewards: list[Reward] = Field(default_factory=list)
    prop_rewards: list[Reward] = Field(default_factory=list)
    info_rewards: list[str] = Field(default_factory=list)   # 怪物信息里的归属掉落（分解精华按它判定）
    effects: list[str] = Field(default_factory=list)


class Encounter(BaseModel):
    monster_id: str
    weight: int = Field(ge=0)


class DungeonDef(BaseModel):
    id: int = Field(ge=1)
    name: str
    stamina: int = Field(default=5, ge=0)
    hidden_id: str = ""
    hidden_rate: int = Field(default=10, ge=0, le=100)
    encounters: list[Encounter] = Field(default_factory=list)
