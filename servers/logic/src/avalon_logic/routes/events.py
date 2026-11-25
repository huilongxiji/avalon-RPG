"""事件流（SSE）：API 后端订阅后转发给网站和模拟器。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from ..auth import require_internal
from ..events import bus

router = APIRouter(prefix="/internal", dependencies=[Depends(require_internal)])
KEEPALIVE_SECONDS = 15


@router.get("/events")
async def events(request: Request) -> StreamingResponse:
    queue = bus.subscribe()

    async def stream() -> AsyncIterator[str]:
        try:
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(stream(), media_type="text/event-stream")
