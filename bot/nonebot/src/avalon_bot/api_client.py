"""调用 API 后端：带服务令牌，并带上发指令的玩家 openid。

返回 data；失败时抛出 GameError（错误码和中文提示来自 API 后端）。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx
from avalon_contracts.errors import GameError

_http: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        from .config import bot_config

        cfg = bot_config()
        headers = {"Authorization": f"Bearer {cfg.avalon_api_token}"} if cfg.avalon_api_token else {}
        _http = httpx.AsyncClient(base_url=cfg.avalon_api_url.rstrip("/"), headers=headers, timeout=120)
    return _http


async def close() -> None:
    global _http
    if _http is not None:
        await _http.aclose()
        _http = None


async def call(method: str, path: str, *, openid: str | None = None, superuser: bool = False,
               request_id: str | None = None, **kwargs: Any) -> Any:
    headers = kwargs.pop("headers", {}) or {}
    if openid:
        headers["X-Player-Openid"] = openid
    headers["X-Actor-Superuser"] = str(superuser).lower()
    if method != "GET":
        headers["Idempotency-Key"] = request_id or str(uuid4())
    try:
        resp = await _client().request(method, path, headers=headers, **kwargs)
    except httpx.HTTPError as exc:
        raise GameError("logic_unavailable", "游戏服务暂时无法访问，请稍后再试") from exc
    try:
        body = resp.json()
    except ValueError as exc:
        raise GameError("internal") from exc
    if resp.is_error and not (isinstance(body, dict) and body.get("ok") is False):
        raise GameError("invalid" if resp.status_code == 422 else "logic_unavailable")
    if isinstance(body, dict) and body.get("ok") is False:
        err = body.get("error") or {}
        raise GameError(err.get("code", "internal"), err.get("message"), **(err.get("detail") or {}))
    return body.get("data") if isinstance(body, dict) and "ok" in body else body


async def get(path: str, **kwargs: Any) -> Any:
    return await call("GET", path, **kwargs)


async def post(path: str, **kwargs: Any) -> Any:
    return await call("POST", path, **kwargs)
