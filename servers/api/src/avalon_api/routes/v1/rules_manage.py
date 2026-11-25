"""网站完整规则管理：只读需登录，预检和写入需编辑者及 CSRF 校验。"""

from typing import Annotated
from urllib.parse import quote

from avalon_contracts.api.rules_manage import RuleCategory, RuleDelete, RuleWrite
from fastapi import APIRouter, Depends

from ...auth.web import current_user, editor_actor
from ...logic_client import logic
from .edit import _who

router = APIRouter(prefix="/api/v1", tags=["完整规则管理"], dependencies=[Depends(current_user)])
Actor = Annotated[str, Depends(editor_actor)]


@router.get("/catalog/manage/meta")
async def meta(draft: bool = False):
    return await logic().get("/internal/rules/manage/meta", params={"draft": draft})


@router.get("/catalog/manage/{category}")
async def listing(category: RuleCategory, draft: bool = False):
    return await logic().get(f"/internal/rules/manage/{category}", params={"draft": draft})


@router.post("/edit/manage/{category}/check")
async def check(category: RuleCategory, body: RuleWrite, actor: Actor, key: str | None = None):
    return await logic().post(f"/internal/rules/manage/{category}/check", json=body.model_dump(mode="json"),
                              params={"key": key} if key is not None else {}, **_who(actor))


@router.post("/edit/manage/{category}")
async def create(category: RuleCategory, body: RuleWrite, actor: Actor):
    return await logic().post(f"/internal/rules/manage/{category}", json=body.model_dump(mode="json"), **_who(actor))


@router.put("/edit/manage/{category}/{key}")
async def update(category: RuleCategory, key: str, body: RuleWrite, actor: Actor):
    return await logic().put(f"/internal/rules/manage/{category}/{quote(key, safe='')}",
                             json=body.model_dump(mode="json"), **_who(actor))


@router.delete("/edit/manage/{category}/{key}")
async def remove(category: RuleCategory, key: str, body: RuleDelete, actor: Actor):
    return await logic().delete(f"/internal/rules/manage/{category}/{quote(key, safe='')}",
                                json=body.model_dump(mode="json"), **_who(actor))
