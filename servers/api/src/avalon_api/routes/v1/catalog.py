"""网站规则查询：仅登录用户可读；服务客户端使用各自的玩家/模拟接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ...auth.web import current_user
from ...logic_client import logic

router = APIRouter(prefix="/api/v1/catalog", tags=["规则数据查询"], dependencies=[Depends(current_user)])


def _q(draft: bool) -> dict[str, Any]:
    return {"params": {"draft": "true"}} if draft else {}


@router.get("/items")
async def items(draft: bool = False) -> Any:
    """全部装备，按主套装分组的卡片。"""
    return await logic().get("/internal/rules/items", **_q(draft))


@router.get("/items/{item_id}")
async def item(item_id: int, draft: bool = False) -> Any:
    """一件装备的详情：全部属性、套装各档位的效果和中文逻辑、伤害计算流程和公式。"""
    return await logic().get(f"/internal/rules/items/{item_id}", **_q(draft))


@router.get("/formulas")
async def formulas(draft: bool = False) -> Any:
    """全部公式：中文名称、原式、中文读法、变量说明。"""
    return await logic().get("/internal/rules/formulas", **_q(draft))


@router.get("/meta")
async def meta(draft: bool = False) -> Any:
    """编辑表单用：全部属性、部位、伤害类型、套装名。"""
    return await logic().get("/internal/rules/meta", **_q(draft))


@router.get("/settings")
async def settings(draft: bool = False) -> Any:
    """游戏数值设定；修改后需校验并激活草稿。"""
    return await logic().get("/internal/rules/settings", **_q(draft))
