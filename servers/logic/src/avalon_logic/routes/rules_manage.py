"""完整规则定义的查询、预检及草稿 CRUD。"""

from typing import Annotated

from avalon_contracts.api.rules_manage import RuleCategory, RuleDelete, RuleRecords, RuleWrite
from avalon_contracts.common import ApiResponse
from fastapi import APIRouter, Depends

from ..auth import require_internal
from ..rules import management
from .rules import actor

router = APIRouter(prefix="/internal/rules/manage", dependencies=[Depends(require_internal)])
Actor = Annotated[str, Depends(actor)]


@router.get("/meta")
async def meta(draft: bool = False):
    return ApiResponse.success(await management.meta(draft))


@router.get("/{category}", response_model=ApiResponse[RuleRecords])
async def listing(category: RuleCategory, draft: bool = False):
    return ApiResponse.success(await management.listing(category, draft))


@router.post("/{category}/check")
async def check(category: RuleCategory, body: RuleWrite, who: Actor, key: str | None = None):
    return ApiResponse.success(await management.save(category, key, body, actor=who, check_only=True))


@router.post("/{category}")
async def create(category: RuleCategory, body: RuleWrite, who: Actor):
    return ApiResponse.success(await management.save(category, None, body, actor=who))


@router.put("/{category}/{key}")
async def update(category: RuleCategory, key: str, body: RuleWrite, who: Actor):
    return ApiResponse.success(await management.save(category, key, body, actor=who))


@router.delete("/{category}/{key}")
async def remove(category: RuleCategory, key: str, body: RuleDelete, who: Actor):
    await management.remove(category, key, body, actor=who)
    return ApiResponse.success(None)
