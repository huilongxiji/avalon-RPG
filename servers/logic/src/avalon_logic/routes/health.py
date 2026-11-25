"""健康检查：编排程序和 API 后端用它判断逻辑后端是否正常。不需要令牌。"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from tortoise import connections

from avalon_contracts.common import Health

from .. import __version__
from ..engine.snapshot import holder
from ..store.orm import DATABASES

router = APIRouter()
STARTED_AT = datetime.now(timezone.utc)


@router.get("/health", response_model=Health)
async def health() -> Health:
    databases: dict[str, bool] = {}
    for name in DATABASES:
        try:
            await connections.get(name).execute_query("SELECT 1")
            databases[name] = True
        except Exception:  # noqa: BLE001 - 健康检查只报告结果
            databases[name] = False
    return Health(
        service="logic",
        ok=all(databases.values()),
        version=__version__,
        started_at=STARTED_AT,
        rules_version=holder.get().version_id,
        extra={"databases": databases},
    )
