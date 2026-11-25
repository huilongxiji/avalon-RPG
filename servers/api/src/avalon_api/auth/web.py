"""网站账号会话与权限。服务令牌不授予网站权限。"""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import urlsplit

from avalon_contracts.errors import GameError
from fastapi import Depends, Request
from starlette.requests import HTTPConnection

from ..store.models import AdminUser, WebSession
from .tokens import hash_token

COOKIE_NAME = "avalon_session"
SESSION_SECONDS = 8 * 60 * 60
ROLES = {"viewer": 0, "editor": 1, "admin": 2, "super": 3}


def credential_version(user: AdminUser) -> str:
    # 手动 SQL 修改密码、用户名或角色，同样使已有会话失效。
    return hash_token(f"{user.username}\0{user.password_hash}\0{user.role}")


def csrf_token(token: str) -> str:
    return hmac.new(token.encode(), b"avalon-web-csrf", hashlib.sha256).hexdigest()


def check_origin(connection: HTTPConnection) -> None:
    origin = connection.headers.get("origin")
    if connection.headers.get("sec-fetch-site") == "cross-site":
        raise GameError("forbidden", "不允许跨站请求")
    if origin:
        try:
            parsed = urlsplit(origin)
        except ValueError:
            raise GameError("forbidden", "请求来源不正确") from None
        # Vite 代理保留 Host；反向代理也应保留外部 Host。
        if parsed.scheme not in {"http", "https"} or parsed.netloc != connection.headers.get("host"):
            raise GameError("forbidden", "请求来源不正确，请从本站重新操作")


async def session_user(connection: HTTPConnection) -> tuple[WebSession, AdminUser]:
    token = connection.cookies.get(COOKIE_NAME, "")
    if not token or len(token) > 128:
        raise GameError("unauthorized", "请先登录网站")
    session = await WebSession.get_or_none(token_hash=hash_token(token)).select_related("user")
    if session is None:
        raise GameError("unauthorized", "登录已失效，请重新登录")
    user = session.user
    if (session.expires_at <= datetime.now(timezone.utc) or user.disabled or user.role not in ROLES
            or not hmac.compare_digest(session.credential_version, credential_version(user))):
        await session.delete()
        raise GameError("unauthorized", "登录已失效，请重新登录")
    return session, user


async def current_user(request: Request) -> AdminUser:
    _, user = await session_user(request)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        check_origin(request)
        supplied = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(supplied.encode(), csrf_token(request.cookies[COOKIE_NAME]).encode()):
            raise GameError("forbidden", "页面校验已失效，请刷新后重试")
    return user


def require_role(role: str):
    async def check(user: Annotated[AdminUser, Depends(current_user)]) -> AdminUser:
        if ROLES[user.role] < ROLES[role]:
            raise GameError("forbidden", "当前账号没有此操作的权限")
        return user
    return check


async def editor_actor(user: Annotated[AdminUser, Depends(require_role("editor"))]) -> str:
    return user.username


async def admin_actor(user: Annotated[AdminUser, Depends(require_role("admin"))]) -> str:
    return user.username


class LoginLimiter:
    """单进程 API 的有界登录限流；代理地址只用于 IP 桶，不信任 X-Forwarded-For。"""

    def __init__(self) -> None:
        self.buckets: dict[str, tuple[float, int]] = {}

    def check(self, username: str, ip: str) -> None:
        now = time.monotonic()
        self.buckets = {k: v for k, v in self.buckets.items() if v[0] > now}
        keys = [("user:" + hash_token(username), 10), ("ip:" + ip, 60)]
        if len(self.buckets) >= 10_000 or any(self.buckets.get(k, (0, 0))[1] >= n for k, n in keys):
            raise GameError("rate_limited", "登录尝试过于频繁，请 15 分钟后再试")
        for key, _ in keys:
            until, count = self.buckets.get(key, (now + 900, 0))
            self.buckets[key] = until, count + 1

    def success(self, username: str) -> None:
        self.buckets.pop("user:" + hash_token(username), None)


login_limiter = LoginLimiter()
