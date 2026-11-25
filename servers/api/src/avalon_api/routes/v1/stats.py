"""统计流水只供已登录的网站账号查看。"""
from typing import Annotated

from avalon_contracts.api.stats import StatsFilter, StatsKind
from fastapi import APIRouter, Depends, Query

from ...auth.web import current_user
from ...logic_client import logic

router = APIRouter(prefix='/api/v1/stats', tags=['统计流水'], dependencies=[Depends(current_user)])


@router.get('/{kind}')
async def stats(kind: StatsKind, filters: Annotated[StatsFilter, Query()]):
    return await logic().get(f'/internal/stats/{kind}', params=filters.model_dump(mode='json', by_alias=True, exclude_none=True))
