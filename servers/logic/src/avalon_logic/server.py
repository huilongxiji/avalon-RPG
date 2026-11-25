"""逻辑后端入口：uvicorn avalon_logic.server:app

只监听本机或内网（端口 7901），由 API 后端调用。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from avalon_contracts.common import ApiResponse
from avalon_contracts.errors import GameError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from tortoise.contrib.fastapi import RegisterTortoise

from . import __version__
from .config import get_settings
from .game.tasks import background_tasks
from .routes import events, game, health, rules, rules_manage, sim, stats
from .store.orm import TORTOISE_ORM, enable_wal

log = logging.getLogger("avalon_logic")


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()
    # 表结构由 avalon-logic-migrate 负责升级，这里不自动建表
    async with RegisterTortoise(app, config=TORTOISE_ORM, generate_schemas=False, add_exception_handlers=False):
        await enable_wal()
        # 读取规则库里当前生效的版本，编译成规则快照
        from .rules import current

        await current.reload()
        from .config import SIM_WORKERS
        from .sim import jobs

        jobs._queue = jobs.JobQueue(get_settings().data_dir / "sim" / "jobs.db", workers=SIM_WORKERS)
        jobs._queue.start()
        log.info("逻辑后端已启动")
        try:
            async with background_tasks():
                yield
        finally:
            await jobs._queue.stop()
            jobs._queue = None
    log.info("逻辑后端已停止")


app = FastAPI(title="阿瓦隆逻辑后端", version=__version__, lifespan=lifespan)


@app.exception_handler(GameError)
async def _game_error(_: Request, exc: GameError) -> JSONResponse:
    status = 401 if exc.code == "unauthorized" else 400
    body = ApiResponse.failure(exc.code, exc.message, **exc.detail)
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


@app.exception_handler(Exception)
async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
    log.exception("未处理的错误", exc_info=exc)
    body = ApiResponse.failure("internal")
    return JSONResponse(status_code=500, content=body.model_dump(mode="json"))


app.include_router(health.router)
app.include_router(events.router)
app.include_router(rules.router)
app.include_router(rules_manage.router)
app.include_router(game.router)
app.include_router(stats.router)
app.include_router(sim.router)
