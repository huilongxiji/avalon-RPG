"""结构化战报。bot 前端、网站、模拟器都按它各自排版，后端不负责排版。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Side = Literal["player", "foe"]


class Hit(BaseModel):
    kind: Literal["physical", "magic", "precision", "true"]
    value: int
    crit: bool = False
    dodged: bool = False
    source: str = ""             # 来自哪个效果（普通攻击为空）


class Turn(BaseModel):
    round: int
    side: Side
    hits: list[Hit] = Field(default_factory=list)
    healed: int = 0
    shield: int = 0
    player_hp: int
    foe_hp: int
    notes: list[str] = Field(default_factory=list)   # 效果说明，如"火纹叠到 3 层"


class BattleReport(BaseModel):
    won: bool
    draw: bool = False           # 平局（到达回合上限，或无限回合下长时间零伤害）
    rounds: int
    player_first: bool
    player_max_hp: int
    foe_max_hp: int
    player_hp: int
    foe_hp: int
    player_damage: int
    foe_damage: int
    turns: list[Turn] = Field(default_factory=list)
    # 各效果触发次数（统计"技能使用次数"用）
    effect_counts: dict[str, int] = Field(default_factory=dict)
    rules_version: int | None = None
    seed: int | None = None
