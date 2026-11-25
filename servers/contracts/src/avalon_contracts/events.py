"""服务之间推送的事件。

逻辑后端发出事件（SSE），API 后端订阅后通过 WebSocket 推给网站和模拟器。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

# 事件类型
RULES_ACTIVATED = "rules.activated"        # 规则版本已激活，客户端应刷新缓存
RULES_DRAFT_CHANGED = "rules.draft_changed"
PLAYER_LEVEL_UP = "player.level_up"
WORLD_BOSS_SETTLED = "world_boss.settled"
SIM_PROGRESS = "sim.progress"              # 模拟任务进度
SIM_FINISHED = "sim.finished"
SERVICE_STATUS = "service.status"          # 编排程序报告的服务状态变化

EVENT_TYPES = (
    RULES_ACTIVATED,
    RULES_DRAFT_CHANGED,
    PLAYER_LEVEL_UP,
    WORLD_BOSS_SETTLED,
    SIM_PROGRESS,
    SIM_FINISHED,
    SERVICE_STATUS,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Event(BaseModel):
    type: str
    at: datetime = Field(default_factory=_now)
    data: dict[str, Any] = Field(default_factory=dict)
