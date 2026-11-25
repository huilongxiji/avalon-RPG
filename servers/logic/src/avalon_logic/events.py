"""事件发布：逻辑后端把事件推给订阅者（API 后端通过 SSE 订阅）。"""

from __future__ import annotations

import asyncio

from avalon_contracts.events import Event

_MAX_QUEUE = 1000


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[Event]] = set()

    def subscribe(self) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=_MAX_QUEUE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Event]) -> None:
        self._subscribers.discard(queue)

    def publish(self, event: Event) -> None:
        for queue in list(self._subscribers):
            if queue.full():
                # 订阅者太慢：丢掉最旧的一条，保证最新状态能送到
                queue.get_nowait()
            queue.put_nowait(event)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


bus = EventBus()
