"""内部令牌校验：只有 API 后端（以及编排程序）能调用逻辑后端。"""

from __future__ import annotations

import hmac
import logging

from fastapi import Header, Request

from avalon_contracts.errors import GameError

from .config import get_settings

log = logging.getLogger("avalon_logic.auth")
_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


async def require_internal(request: Request, x_internal_token: str = Header(default="")) -> None:
    token = get_settings().internal_token
    if not token:
        # 未配置令牌：只允许本机访问（开发时用）
        client = request.client.host if request.client else ""
        if client not in _LOCAL_HOSTS:
            raise GameError("unauthorized")
        return
    if not hmac.compare_digest(x_internal_token, token):
        raise GameError("unauthorized")
