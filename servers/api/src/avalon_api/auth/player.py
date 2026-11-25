"""可信 bot 代理玩家身份。模拟令牌即使伪造玩家或超管头也不能访问。

超管标记只能由验证过 NoneBot SUPERUSER 的 bot 提供；它不是网站管理员令牌。
"""

from __future__ import annotations

import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Annotated

from avalon_contracts.errors import GameError
from fastapi import Depends, Header, Request

from ..store.models import ServiceToken
from .service import _current_token


@dataclass(frozen=True)
class PlayerActor:
    openid: str
    superuser: bool


class RateLimiter:
    def __init__(self, limit: int = 120, seconds: float = 60, max_keys: int = 10000):
        self.limit, self.seconds, self.max_keys = limit, seconds, max_keys
        self.windows: OrderedDict[str, deque] = OrderedDict()

    def check(self, key: str) -> None:
        now = time.monotonic()
        window = self.windows.pop(key, deque())
        while window and window[0] <= now - self.seconds:
            window.popleft()
        self.windows[key] = window
        if len(self.windows) > self.max_keys:
            self.windows.popitem(last=False)
        if len(window) >= self.limit:
            raise GameError("rate_limited")
        window.append(now)


limiter = RateLimiter()


async def player_actor(request: Request, token: Annotated[ServiceToken, Depends(_current_token)],
                       x_player_openid: str = Header(default=""),
                       x_actor_superuser: str = Header(default="false")) -> PlayerActor:
    if token.name != "bot" or "player" not in (token.scopes or []):
        raise GameError("forbidden")
    if not x_player_openid or len(x_player_openid) > 64 or x_player_openid.strip() != x_player_openid:
        raise GameError("invalid", "缺少有效的玩家身份")
    if x_actor_superuser not in ("true", "false"):
        raise GameError("invalid", "超管标记格式不正确")
    actor = PlayerActor(x_player_openid, x_actor_superuser == "true")
    limiter.check(f"{token.id}:{actor.openid}")
    request.state.player_actor = actor
    return actor
