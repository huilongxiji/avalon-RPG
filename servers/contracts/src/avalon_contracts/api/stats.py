"""本机管理后台的统计查询参数。日期按游戏时区，首尾日期都包含。"""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

StatsKind = Literal['overview', 'economy', 'battles', 'drops', 'effects']


class StatsFilter(BaseModel):
    from_date: date | None = Field(default=None, alias='from')
    to_date: date | None = Field(default=None, alias='to')
    openid: str = Field(default='', max_length=64)
    source: str = Field(default='', max_length=32)
    currency: str = Field(default='', max_length=16)
    dungeon_id: int | None = Field(default=None, ge=1)
    monster_id: str = Field(default='', max_length=64)
    item_name: str = Field(default='', max_length=128)
    page: int = Field(default=1, ge=1, le=1000000)
    size: int = Field(default=50, ge=1, le=200)
