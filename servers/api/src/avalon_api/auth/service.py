"""服务令牌：请求头 Authorization: Bearer <令牌>。

令牌以 servers/.env 为准，API 后端启动时同步进 api.db（只存哈希值）：
- bot：只能调玩家接口（player）
- sim：只能调模拟接口（sim）——模拟器只跑模拟，不能改数据
网站管理接口只接受网站会话，服务令牌不能登录网站或管理账号。
"""

from __future__ import annotations

import logging

from fastapi import Depends, Header

from avalon_contracts.errors import GameError

from ..config import get_settings
from ..store.models import ServiceToken
from .tokens import SCOPES, hash_token

log = logging.getLogger("avalon_api.auth")


async def ensure_service_tokens() -> None:
    """把 .env 里的令牌同步进 api.db：新的就登记，改过的就更新哈希。"""
    for name, token in get_settings().service_tokens.items():
        token_hash = hash_token(token)
        row = await ServiceToken.get_or_none(name=name)
        if row is None:
            await ServiceToken.create(name=name, token_hash=token_hash, scopes=SCOPES.get(name, []))
            log.info("已登记服务令牌：%s", name)
        elif row.token_hash != token_hash or row.scopes != SCOPES.get(name, []) or row.revoked:
            row.token_hash = token_hash
            row.scopes = SCOPES.get(name, [])
            row.revoked = False
            await row.save()
            log.info("已更新服务令牌：%s", name)


async def _current_token(authorization: str = Header(default="")) -> ServiceToken:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise GameError("unauthorized")
    row = await ServiceToken.get_or_none(token_hash=hash_token(token.strip()), revoked=False)
    if row is None:
        raise GameError("unauthorized")
    return row


def require_scope(scope: str):
    """依赖项：要求令牌拥有指定权限，否则返回"没有权限"。"""

    async def checker(row: ServiceToken = Depends(_current_token)) -> ServiceToken:
        if scope not in (row.scopes or []):
            raise GameError("forbidden")
        return row

    return checker
