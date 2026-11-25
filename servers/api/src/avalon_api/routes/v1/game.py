"""对外玩家接口：验证身份、限流、转发。没有游戏计算或存档访问。"""

from __future__ import annotations

import inspect
import re
import uuid
from typing import Any
from urllib.parse import quote

from avalon_contracts.api.game import OPERATIONS, Operation
from avalon_contracts.api.game_views import RESPONSES
from avalon_contracts.common import ApiResponse
from avalon_contracts.errors import GameError
from fastapi import APIRouter, Body, Depends, Path, Request

from ...auth.player import player_actor
from ...logic_client import logic

router = APIRouter(prefix="/api/v1", tags=["玩家"], dependencies=[Depends(player_actor)])


def endpoint(operation: Operation):
    async def handle(request: Request, **values: Any):
        actor = request.state.player_actor
        if operation.admin and not actor.superuser:
            raise GameError("forbidden")
        owner = values.get("openid", actor.openid)
        if owner != actor.openid and not operation.admin:
            raise GameError("forbidden", "只能操作自己的角色")
        request_id = request.headers.get("Idempotency-Key", "") or str(uuid.uuid4())
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", request_id):
            raise GameError("invalid", "请求编号格式不正确")
        headers = {"X-Player-Openid": actor.openid, "X-Actor-Superuser": str(actor.superuser).lower(),
                   "Idempotency-Key": request_id}
        path = operation.path
        for name in re.findall(r"\{(\w+)\}", operation.path):
            path = path.replace("{" + name + "}", quote(str(values[name]), safe=""))
        kwargs = {"headers": headers, "params": dict(request.query_params)}
        if operation.body is not None:
            kwargs["json"] = values["body"].model_dump(mode="json")
        return await logic().request(operation.method, "/internal/game" + path, **kwargs)

    # 显式签名让每条资源路由生成准确的请求体/路径参数 OpenAPI，而非不透明 RPC。
    parameters = [inspect.Parameter("request", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Request)]
    for name in re.findall(r"\{(\w+)\}", operation.path):
        annotation = int if name in ("id", "index", "group_id") else str
        parameters.append(inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY, annotation=annotation,
                                            default=Path(..., ge=0 if operation.key == "item" else 1) if annotation is int else Path(..., min_length=1, max_length=128)))
    if operation.body:
        parameters.append(inspect.Parameter("body", inspect.Parameter.KEYWORD_ONLY, annotation=operation.body, default=Body(...)))
    handle.__signature__ = inspect.Signature(parameters)
    handle.__name__ = operation.key
    return handle


for operation in OPERATIONS:
    router.add_api_route(operation.path, endpoint(operation), methods=[operation.method], summary=operation.title,
                         operation_id="game_" + operation.key, response_model=ApiResponse[RESPONSES[operation.key]])
