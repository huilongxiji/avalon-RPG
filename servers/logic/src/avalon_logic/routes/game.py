"""内部玩家 HTTP 路由：只接收带内部令牌的网关请求。"""

from __future__ import annotations

import inspect
import re
from typing import Any

from avalon_contracts.api.game import OPERATIONS, Operation
from avalon_contracts.api.game_views import RESPONSES
from avalon_contracts.common import ApiResponse
from avalon_contracts.errors import GameError
from fastapi import APIRouter, Body, Depends, Path, Request

from ..auth import require_internal
from ..game.operations import execute

router = APIRouter(prefix="/internal/game", tags=["内部玩家"], dependencies=[Depends(require_internal)])


def endpoint(operation: Operation):
    async def handle(request: Request, **values: Any):
        actor = request.headers.get("X-Player-Openid", "")
        if not actor or len(actor) > 64:
            raise GameError("unauthorized")
        superuser = request.headers.get("X-Actor-Superuser", "false") == "true"
        body = values.pop("body", None)
        data = await execute(operation, actor, superuser, values, dict(request.query_params), body,
                             request.headers.get("Idempotency-Key", ""))
        return ApiResponse.success(data)

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
                         operation_id="internal_game_" + operation.key, response_model=ApiResponse[RESPONSES[operation.key]])
