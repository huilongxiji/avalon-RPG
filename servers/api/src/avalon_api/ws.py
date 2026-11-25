"""WebSocket：网站大屏和模拟器接收实时事件（规则激活、模拟进度……）。"""

from __future__ import annotations

import asyncio

from avalon_contracts.errors import GameError
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .auth.service import _current_token
from .auth.web import check_origin, session_user
from .logic_client import logic
from .relay import relay

router = APIRouter()


@router.websocket("/ws/live")
async def live(ws: WebSocket) -> None:
    try:
        check_origin(ws)
        await session_user(ws)
    except GameError:
        await ws.close(code=1008)
        return
    await ws.accept()
    queue = relay.subscribe()
    try:
        while True:
            await session_user(ws)
            try:
                event = await asyncio.wait_for(queue.get(), timeout=5)
            except TimeoutError:
                continue
            await session_user(ws)
            await ws.send_text(event.model_dump_json())
    except (WebSocketDisconnect, OSError):
        pass
    except GameError:
        await ws.close(code=1008)
    finally:
        relay.unsubscribe(queue)


@router.websocket("/ws/sim/{job_id}")
async def simulation(ws: WebSocket, job_id: int) -> None:
    """桌面客户端用 Authorization 请求头鉴权，令牌不进入 URL 或日志。"""
    authorization = ws.headers.get("authorization", "")
    accepted = False
    previous = None
    try:
        while True:
            caller = await _current_token(authorization)
            if "sim" not in (caller.scopes or []):
                raise GameError("forbidden")
            result = await logic().get(f"/internal/sim/jobs/{job_id}", headers={"X-Sim-Owner": str(caller.id)})
            if not accepted:
                await ws.accept()
                accepted = True
            if result != previous:
                await ws.send_json(result)
                previous = result
            if result["data"]["status"] in {"finished", "failed", "cancelled"}:
                await ws.close(code=1000)
                return
            await asyncio.sleep(.5)
    except (WebSocketDisconnect, OSError):
        pass
    except GameError:
        await ws.close(code=1008)
