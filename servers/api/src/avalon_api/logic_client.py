"""调用逻辑后端（带内部令牌）。连不上时统一报"逻辑后端暂时无法访问"。"""

from __future__ import annotations

from typing import Any

import httpx
from avalon_contracts.errors import GameError

from .config import LOGIC_URL, get_settings


class LogicClient:
    def __init__(self) -> None:
        settings = get_settings()
        headers = {"X-Internal-Token": settings.internal_token} if settings.internal_token else {}
        self.base_url = LOGIC_URL
        self.http = httpx.AsyncClient(base_url=LOGIC_URL, headers=headers, timeout=120)

    async def close(self) -> None:
        await self.http.aclose()

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            resp = await self.http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise GameError("logic_unavailable") from exc
        try:
            body = resp.json()
        except ValueError as exc:
            raise GameError("internal", detail_status=resp.status_code) from exc
        if resp.is_error and not (isinstance(body, dict) and body.get("ok") is False):
            raise GameError("invalid" if resp.status_code == 422 else "logic_unavailable")
        if isinstance(body, dict) and body.get("ok") is False and body.get("error"):
            err = body["error"]
            raise GameError(err.get("code", "internal"), err.get("message"), **(err.get("detail") or {}))
        return body

    async def get(self, path: str, **kwargs: Any) -> Any:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> Any:
        return await self.request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs: Any) -> Any:
        return await self.request("PUT", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> Any:
        return await self.request("DELETE", path, **kwargs)


_client: LogicClient | None = None


def logic() -> LogicClient:
    if _client is None:
        raise RuntimeError("逻辑后端客户端还没有初始化")
    return _client


async def open_client() -> None:
    global _client
    _client = LogicClient()


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
