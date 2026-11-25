"""玩家接口格式（M4 阶段补全各玩法的请求与返回）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PlayerRef(BaseModel):
    openid: str = Field(min_length=1, max_length=64)
    name: str = ""


class PanelView(BaseModel):
    """面板：最终属性（含装备、强化、淬炼、套装）。"""

    openid: str
    level: int
    exp: int
    exp_to_next: int
    stats: dict[str, float]
    coins: int
    world_coins: int
    stamina: int
    special_stamina: int
