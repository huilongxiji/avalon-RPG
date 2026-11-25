"""健康检查：给编排程序用。

- /health          bot 前端本身是否在运行
- /health/onebot   goqbot 是否已经连上（没连上返回 503）
"""

from __future__ import annotations

from datetime import datetime, timezone

from avalon_contracts.common import Health
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from nonebot import get_app, get_bots, get_driver
from nonebot.plugin import PluginMetadata

from ... import __version__
from ...api_client import close

__plugin_meta__ = PluginMetadata(
    name="健康检查",
    description="向编排程序报告 bot 前端和 goqbot 的连接状态",
    usage="无指令",
    type="application",
)

STARTED_AT = datetime.now(timezone.utc)
app: FastAPI = get_app()


@app.get("/health")
async def health() -> dict:
    bots = get_bots()
    return Health(
        service="bot", version=__version__, started_at=STARTED_AT,
        extra={"onebot_connected": len(bots), "bots": list(bots)},
    ).model_dump(mode="json")


@app.get("/health/onebot")
async def onebot() -> JSONResponse:
    bots = get_bots()
    body = {"connected": len(bots), "bots": list(bots)}
    return JSONResponse(status_code=200 if bots else 503, content=body)


@get_driver().on_shutdown
async def _close_api_client() -> None:
    await close()
