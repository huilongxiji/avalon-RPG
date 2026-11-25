"""运行概览：实际健康检查和 OneBot 连接状态。

网站会话可读取；健康摘要兼容机器人与模拟器的服务令牌。
"""

from __future__ import annotations

import asyncio
from typing import Any

from avalon_contracts.api.system import ServiceState
from avalon_contracts.common import ApiResponse
from avalon_contracts.errors import GameError
from fastapi import APIRouter, Depends, Request

from ...auth.service import _current_token
from ...auth.web import COOKIE_NAME, current_user
from ...logic_client import logic
from ...service_status import PROBE_TIMEOUT, service_states

router = APIRouter(prefix="/api/v1/system", tags=["系统"])


async def health_access(request: Request):
    if request.cookies.get(COOKIE_NAME):
        return await current_user(request)
    token = await _current_token(request.headers.get("authorization", ""))
    if not {"sim", "player"}.intersection(token.scopes or []):
        raise GameError("forbidden")
    return token


@router.get("/health", response_model=ApiResponse[dict[str, Any]], dependencies=[Depends(health_access)])
async def system_health() -> ApiResponse[dict[str, Any]]:
    result: dict[str, Any] = {"api": True}
    try:
        async with asyncio.timeout(PROBE_TIMEOUT):
            result["logic"] = await logic().get("/health", timeout=PROBE_TIMEOUT)
    except Exception:  # noqa: BLE001
        result["logic"] = None
    return ApiResponse.success(result)


@router.get("/services", response_model=ApiResponse[list[ServiceState]], dependencies=[Depends(current_user)])
async def services() -> ApiResponse[list[ServiceState]]:
    """探测实际服务；不依赖根入口提供额外编排接口。"""
    return ApiResponse.success(await service_states())
