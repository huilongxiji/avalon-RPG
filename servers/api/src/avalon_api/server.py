"""API 后端入口：uvicorn avalon_api.server:app（端口 7900）。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from avalon_contracts.common import ApiResponse, Health
from avalon_contracts.errors import GameError
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from tortoise.contrib.fastapi import RegisterTortoise

from . import __version__
from .auth.service import ensure_service_tokens
from .config import get_settings
from .logic_client import close_client, open_client
from .relay import relay
from .routes.v1 import accounts, catalog, edit, game, rules, rules_manage, sim, stats, system
from .static import mount_web
from .store.orm import TORTOISE_ORM, enable_wal
from .ws import router as ws_router

log = logging.getLogger("avalon_api")
STARTED_AT = datetime.now(timezone.utc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()
    async with RegisterTortoise(app, config=TORTOISE_ORM, generate_schemas=False, add_exception_handlers=False):
        await enable_wal()
        await ensure_service_tokens()
        await open_client()
        relay.start()
        log.info("API 后端已启动")
        yield
        await relay.stop()
        await close_client()
    log.info("API 后端已停止")


app = FastAPI(title="阿瓦隆 API", version=__version__, lifespan=lifespan)


@app.middleware("http")
async def website_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.exception_handler(GameError)
async def _game_error(_: Request, exc: GameError) -> JSONResponse:
    status = {"unauthorized": 401, "forbidden": 403, "logic_unavailable": 503, "rate_limited": 429,
              "conflict": 409, "rules_conflict": 409, "website_user_not_found": 404}.get(exc.code, 400)
    body = ApiResponse.failure(exc.code, exc.message, **exc.detail)
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


_FIELD_NAMES = {"name": "名称", "slot": "部位", "price": "价格", "stats": "属性", "damage_type": "伤害类型",
                "sets": "套装", "expr": "原式", "params": "变量", "title": "中文名称", "id": "编号"}


def _message(error: dict) -> str:
    """把数据校验的英文提示换成中文。"""
    ctx = error.get("ctx") or {}
    kind = error.get("type", "")
    table = {
        "missing": "必须填写",
        "greater_than_equal": f"不能小于 {ctx.get('ge')}",
        "greater_than": f"要大于 {ctx.get('gt')}",
        "less_than_equal": f"不能大于 {ctx.get('le')}",
        "string_pattern_mismatch": "格式不对：只能用中文、字母、数字和下划线，不能以数字或下划线开头",
        "string_too_short": "不能为空",
        "string_too_long": f"最多 {ctx.get('max_length')} 个字",
        "too_short": f"至少要 {ctx.get('min_length')} 个",
        "too_long": f"最多 {ctx.get('max_length')} 个",
        "literal_error": f"只能是：{ctx.get('expected')}",
        "int_parsing": "要填整数", "int_from_float": "要填整数",
        "float_parsing": "要填数字", "bool_parsing": "要选是或否",
        "string_type": "要填文字", "dict_type": "格式不对", "list_type": "格式不对",
    }
    return table.get(kind, "格式不对")


@app.exception_handler(RequestValidationError)
async def _invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
    """提交的数据格式不对（例如价格填了负数、公式代号以数字开头）。"""
    problems = []
    for error in exc.errors():
        where = "、".join(_FIELD_NAMES.get(str(p), str(p)) for p in error.get("loc", ())[1:]) or "提交的内容"
        problems.append(f"{where}：{_message(error)}")
    body = ApiResponse.failure("invalid", "填写的内容不正确：" + "；".join(problems), problems=problems)
    return JSONResponse(status_code=422, content=body.model_dump(mode="json"))


@app.exception_handler(Exception)
async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
    log.exception("未处理的错误", exc_info=exc)
    return JSONResponse(status_code=500, content=ApiResponse.failure("internal").model_dump(mode="json"))


@app.get("/health", response_model=Health)
async def health() -> Health:
    return Health(service="api", version=__version__, started_at=STARTED_AT)


app.include_router(system.router)
app.include_router(accounts.router)
app.include_router(rules.router)
app.include_router(rules_manage.router)
app.include_router(catalog.router)
app.include_router(edit.router)
app.include_router(game.router)
app.include_router(stats.router)
app.include_router(sim.router)
app.include_router(ws_router)
# 网站静态文件最后挂载，避免盖住接口路径
mount_web(app)
