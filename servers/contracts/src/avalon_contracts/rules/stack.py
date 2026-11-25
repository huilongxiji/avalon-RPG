"""层数定义：碎晶、沉沦印记、火纹……战斗中会增减的计数。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class StackDef(BaseModel):
    key: str = Field(min_length=1)       # 表达式里用 self.stacks.<key> / foe.stacks.<key>，可以是中文
    name: str
    owner: Literal["self", "foe"] = "foe"
    max: int | None = None               # 上限；不填为不限
    max_stat: str | None = None          # 施加者的这个属性大于 0 时用它当上限（例如火痕上限由套装提高）
    carry: bool = False                  # 是否跨场保留（爬塔、连战）
    boss_immune: bool = True             # 世界BOSS是否免疫
