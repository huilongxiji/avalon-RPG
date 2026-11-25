"""事件转发：订阅逻辑后端的事件流（SSE），转发给所有连着 WebSocket 的网站和模拟器。

逻辑后端重启或暂时断开时自动重连。
"""

from __future__ import annotations

import asyncio
import json
import logging

import httpx

from avalon_contracts.events import Event

from .config import LOGIC_URL, get_settings

log = logging.getLogger("avalon_api.relay")


class Relay:
    def __init__(self) -> None:
        self._clients: set[asyncio.Queue[Event]] = set()
        self._task: asyncio.Task[None] | None = None

    def subscribe(self) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=500)
        self._clients.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Event]) -> None:
        self._clients.discard(queue)

    def broadcast(self, event: Event) -> None:
        for queue in list(self._clients):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        settings = get_settings()
        headers = {"X-Internal-Token": settings.internal_token} if settings.internal_token else {}
        delay = 1
        while True:
            try:
                async with httpx.AsyncClient(base_url=LOGIC_URL, headers=headers, timeout=None) as http:
                    async with http.stream("GET", "/internal/events") as resp:
                        resp.raise_for_status()
                        delay = 1
                        async for line in resp.aiter_lines():
                            if line.startswith("data: "):
                                try:
                                    self.broadcast(Event.model_validate(json.loads(line[6:])))
                                except ValueError:
                                    log.warning("收到无法解析的事件：%s", line[:200])
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - 断线后重连
                log.debug("事件流断开：%s，%s 秒后重连", exc, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


relay = Relay()
