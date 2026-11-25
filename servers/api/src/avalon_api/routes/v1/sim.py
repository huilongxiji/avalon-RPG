"""模拟令牌接口：原桌面只读图鉴；辅助工具的计算任务转交逻辑后端。"""

from typing import Annotated

from avalon_contracts.api.sim import (
    SimBattleRequest,
    SimCompareRequest,
    SimJobRequest,
    SimStatsRequest,
)
from fastapi import APIRouter, Depends, Query

from ...auth.service import require_scope
from ...logic_client import logic
from ...store.models import ServiceToken

router = APIRouter(prefix="/api/v1/sim", tags=["模拟"], dependencies=[Depends(require_scope("sim"))])
Caller = Annotated[ServiceToken, Depends(require_scope("sim"))]


def _headers(caller: ServiceToken) -> dict[str, str]:
    return {"X-Sim-Owner": str(caller.id)}


@router.get("/catalog")
async def catalog(rules: str = "active"):
    return await logic().get("/internal/sim/catalog", params={"rules": rules})


@router.get("/desktop/catalog")
async def desktop_catalog():
    return await logic().get("/internal/sim/desktop/catalog")


@router.post("/stats")
async def stats(body: SimStatsRequest):
    return await logic().post("/internal/sim/stats", json=body.model_dump(mode="json"))


@router.post("/battle")
async def battle(body: SimBattleRequest, caller: Caller):
    return await logic().post("/internal/sim/battle", json=body.model_dump(mode="json"), headers=_headers(caller))


@router.post("/jobs")
async def create_job(body: SimJobRequest, caller: Caller):
    return await logic().post("/internal/sim/jobs", json=body.model_dump(mode="json"), headers=_headers(caller))


@router.get("/jobs")
async def list_jobs(caller: Caller, limit: int = Query(default=50, ge=1, le=200)):
    return await logic().get("/internal/sim/jobs", params={"limit": limit}, headers=_headers(caller))


@router.get("/jobs/{job_id}")
async def get_job(job_id: int, caller: Caller):
    return await logic().get(f"/internal/sim/jobs/{job_id}", headers=_headers(caller))


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: int, caller: Caller):
    return await logic().delete(f"/internal/sim/jobs/{job_id}", headers=_headers(caller))


@router.get("/jobs/{job_id}/report")
async def report(job_id: int, caller: Caller):
    return await logic().get(f"/internal/sim/jobs/{job_id}/report", headers=_headers(caller))


@router.get("/jobs/{job_id}/samples")
async def samples(job_id: int, caller: Caller):
    return await logic().get(f"/internal/sim/jobs/{job_id}/samples", headers=_headers(caller))


@router.post("/compare")
async def compare(body: SimCompareRequest, caller: Caller):
    return await logic().post("/internal/sim/compare", json=body.model_dump(mode="json"), headers=_headers(caller))


@router.get("/presets")
async def presets():
    return await logic().get("/internal/sim/presets")
