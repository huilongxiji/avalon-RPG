"""系统状态：各服务是否在运行（网站右上角和"系统状态"页使用）。

网站会话可读取；健康摘要兼容机器人与模拟器的服务令牌。
"""

from __future__ import annotations

from typing import Any

import httpx
from avalon_contracts.api.system import ServiceState
from avalon_contracts.common import ApiResponse
from avalon_contracts.errors import GameError
from fastapi import APIRouter, Depends, Request

from ...auth.service import _current_token
from ...auth.web import COOKIE_NAME, current_user
from ...config import CTL_URL
from ...logic_client import logic

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
        result["logic"] = await logic().get("/health")
    except Exception:  # noqa: BLE001
        result["logic"] = None
    return ApiResponse.success(result)


@router.get("/services", response_model=ApiResponse[list[ServiceState]], dependencies=[Depends(current_user)])
async def services() -> ApiResponse[list[ServiceState]]:
    """来自编排程序的状态接口；编排程序没在运行时返回空列表并说明原因。"""
    url = CTL_URL + "/status"
    try:
        async with httpx.AsyncClient(timeout=3) as http:
            resp = await http.get(url)
            resp.raise_for_status()
            states = [ServiceState.model_validate(s) for s in resp.json()]
    except Exception:  # noqa: BLE001
        return ApiResponse(ok=True, data=[], error=None)
    return ApiResponse.success(states)
