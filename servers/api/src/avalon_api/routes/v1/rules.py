"""规则兼容查询接口：仅已登录的网站管理员可用。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ...auth.web import require_role
from ...logic_client import logic

router = APIRouter(prefix="/api/v1/admin/rules", tags=["规则"], dependencies=[Depends(require_role("admin"))])


@router.get("/versions")
async def versions() -> Any:
    return await logic().get("/internal/rules/versions")


@router.post("/expr/check")
async def expr_check(body: dict[str, Any]) -> Any:
    return await logic().post("/internal/rules/expr/check", json=body)
