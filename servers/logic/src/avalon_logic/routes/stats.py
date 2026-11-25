from typing import Annotated

from avalon_contracts.api.stats import StatsFilter, StatsKind
from avalon_contracts.common import ApiResponse
from fastapi import APIRouter, Depends, Query

from ..auth import require_internal
from ..game import statistics

router = APIRouter(prefix='/internal/stats', dependencies=[Depends(require_internal)])


@router.get('/{kind}', response_model=ApiResponse[dict])
async def stats(kind: StatsKind, filters: Annotated[StatsFilter, Query()]):
    return ApiResponse.success(await statistics.query(kind, filters))
