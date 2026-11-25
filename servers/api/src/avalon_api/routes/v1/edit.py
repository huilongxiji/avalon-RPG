"""网站规则编辑：编辑者修改草稿，管理员激活和回滚。"""

from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import quote

from avalon_contracts.rules.formula import FormulaDef
from avalon_contracts.rules.item import ItemDef
from avalon_contracts.rules.setting import SettingDef
from fastapi import APIRouter, Depends

from ...auth.web import ROLES, admin_actor, current_user, editor_actor
from ...logic_client import logic
from ...store.models import AdminUser

router = APIRouter(prefix="/api/v1/edit", tags=["修改规则"], dependencies=[Depends(current_user)])


@router.put("/draft/settings/{key}")
async def update_setting(key: str, body: SettingDef, actor: Annotated[str, Depends(editor_actor)]) -> Any:
    return await logic().put(f"/internal/rules/draft/settings/{quote(key, safe='')}",
                             json=body.model_dump(mode="json"), **_who(actor))


def _who(actor: str) -> dict[str, Any]:
    return {"headers": {"X-Rules-Actor": quote(actor)}}


@router.put('/draft/settings')
async def update_settings(body: list[SettingDef], actor: Annotated[str, Depends(editor_actor)]) -> Any:
    return await logic().put('/internal/rules/draft/settings', json=[s.model_dump(mode='json') for s in body], **_who(actor))


@router.get("/draft")
async def draft_state(user: Annotated[AdminUser, Depends(current_user)]) -> Any:
    body = await logic().get("/internal/rules/draft")
    body["data"]["editable"] = ROLES[user.role] >= ROLES["editor"]
    body["data"]["publishable"] = ROLES[user.role] >= ROLES["admin"]
    return body


@router.get("/versions")
async def versions() -> Any:
    return await logic().get("/internal/rules/versions")


@router.post("/draft")
async def create_draft(actor: Annotated[str, Depends(editor_actor)], body: dict[str, Any] | None = None) -> Any:
    return await logic().post("/internal/rules/draft", json={"note": (body or {}).get("note", "")}, **_who(actor))


@router.delete("/draft")
async def discard_draft(actor: Annotated[str, Depends(editor_actor)]) -> Any:
    return await logic().delete("/internal/rules/draft", **_who(actor))


@router.get("/draft/diff")
async def draft_diff() -> Any:
    return await logic().get("/internal/rules/draft/diff")


@router.post("/draft/validate")
async def validate(actor: Annotated[str, Depends(editor_actor)]) -> Any:
    return await logic().post("/internal/rules/draft/validate", **_who(actor))


@router.post("/draft/activate")
async def activate(actor: Annotated[str, Depends(admin_actor)]) -> Any:
    return await logic().post("/internal/rules/draft/activate", **_who(actor))


@router.post("/versions/{version_id}/rollback")
async def rollback(version_id: int, actor: Annotated[str, Depends(admin_actor)]) -> Any:
    return await logic().post(f"/internal/rules/versions/{version_id}/rollback", **_who(actor))


@router.post("/expr/check")
async def expr_check(body: dict[str, Any]) -> Any:
    """检查表达式（编辑框实时检查用，不改数据）。"""
    return await logic().post("/internal/rules/expr/check", json=body)


@router.post("/draft/items")
async def create_item(body: ItemDef, actor: Annotated[str, Depends(editor_actor)]) -> Any:
    return await logic().post("/internal/rules/draft/items", json=body.model_dump(mode="json"), **_who(actor))


@router.put("/draft/items/{item_id}")
async def update_item(item_id: int, body: ItemDef, actor: Annotated[str, Depends(editor_actor)]) -> Any:
    return await logic().put(f"/internal/rules/draft/items/{item_id}", json=body.model_dump(mode="json"),
                             **_who(actor))


@router.delete("/draft/items/{item_id}")
async def delete_item(item_id: int, actor: Annotated[str, Depends(editor_actor)]) -> Any:
    return await logic().delete(f"/internal/rules/draft/items/{item_id}", **_who(actor))


@router.post("/draft/formulas")
async def create_formula(body: FormulaDef, actor: Annotated[str, Depends(editor_actor)]) -> Any:
    return await logic().post("/internal/rules/draft/formulas", json=body.model_dump(mode="json"), **_who(actor))


@router.put("/draft/formulas/{name}")
async def update_formula(name: str, body: FormulaDef, actor: Annotated[str, Depends(editor_actor)]) -> Any:
    return await logic().put(f"/internal/rules/draft/formulas/{quote(name, safe='')}",
                             json=body.model_dump(mode="json"), **_who(actor))


@router.delete("/draft/formulas/{name}")
async def delete_formula(name: str, actor: Annotated[str, Depends(editor_actor)]) -> Any:
    return await logic().delete(f"/internal/rules/draft/formulas/{quote(name, safe='')}", **_who(actor))
