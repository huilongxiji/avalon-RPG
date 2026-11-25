"""各服务运行状态；探测无法获知的进程信息留空。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ServiceStatus = Literal["starting", "running", "unhealthy", "restarting", "stopped", "offline", "external"]

STATUS_LABELS = {
    "starting": "启动中",
    "running": "运行中",
    "unhealthy": "无响应",
    "restarting": "重启中",
    "stopped": "已停止",
    "offline": "断线",
    "external": "自行管理",
}


class ServiceState(BaseModel):
    key: str
    name: str
    status: ServiceStatus
    pid: int | None = None
    restarts: int | None = None
    last_ok: datetime | None = None
    message: str = ""
