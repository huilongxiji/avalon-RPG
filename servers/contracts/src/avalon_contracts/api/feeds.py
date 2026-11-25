"""一键导出 Excel 与本地 Excel 实时数据源。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

FeedFormat = Literal["html", "csv", "json", "iqy"]


class FeedTokenInfo(BaseModel):
    id: int
    owner: str
    note: str = ""
    created_at: datetime | None = None
    revoked: bool = False
