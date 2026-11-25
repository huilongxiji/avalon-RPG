"""模拟接口。玩家数据和线上业务接口均不在调用链中。"""

from typing import Annotated

from avalon_contracts.api.sim import (
    SimBattleRequest,
    SimCompareRequest,
    SimJobRequest,
    SimStatsRequest,
)
from avalon_contracts.common import ApiResponse
from fastapi import APIRouter, Depends, Header, Query

from ..auth import require_internal
from ..sim import compute, desktop, jobs
from ..sim.snapshot import DATA, capture

router = APIRouter(prefix="/internal/sim", dependencies=[Depends(require_internal)])
Owner = Annotated[str, Header(alias="X-Sim-Owner", min_length=1)]


@router.get("/catalog")
async def catalog(rules: str = "active"):
    version, digest, snapshot = await capture(rules)
    return ApiResponse.success({"rules_version": version, "rules_digest": digest,
                                **snapshot,
                                "supported_jobs": compute.SUPPORTED})


@router.get("/desktop/catalog")
async def desktop_catalog():
    return ApiResponse.success(await desktop.catalog())


@router.post("/stats")
async def stats(body: SimStatsRequest):
    version, digest, snapshot = await capture(body.rules)
    result = compute.stats(DATA.validate_python(snapshot).compile(version), body.loadout)
    return ApiResponse.success({**result, "rules_digest": digest})


async def submit(body: SimJobRequest, owner: str):
    version, digest, snapshot = await capture(body.rules)
    return jobs.queue().submit(owner, body, version, digest, snapshot)


@router.post("/battle")
async def battle(body: SimBattleRequest, owner: Owner):
    request = SimJobRequest(type="world_boss" if body.target == "world_boss" else "batch",
                            rules=body.rules, loadouts=[body.loadout], targets=[body.target],
                            runs=body.runs, seed=body.seed, params=body.params)
    job = await submit(request, owner)
    if body.runs <= 200:
        job = await jobs.queue().wait(job.id, owner)
    result = {"job": job.model_dump(), "report": jobs.queue().report(job.id, owner)
              if job.status == "finished" else None}
    return ApiResponse.success(result)


@router.post("/jobs")
async def create_job(body: SimJobRequest, owner: Owner):
    return ApiResponse.success(await submit(body, owner))


@router.get("/jobs")
async def list_jobs(owner: Owner, limit: int = Query(default=50, ge=1, le=200)):
    return ApiResponse.success(jobs.queue().list(owner, limit))


@router.get("/jobs/{job_id}")
async def get_job(job_id: int, owner: Owner):
    return ApiResponse.success(jobs.queue().get(job_id, owner))


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: int, owner: Owner):
    return ApiResponse.success(jobs.queue().cancel(job_id, owner))


@router.get("/jobs/{job_id}/report")
async def report(job_id: int, owner: Owner):
    return ApiResponse.success(jobs.queue().report(job_id, owner))


@router.get("/jobs/{job_id}/samples")
async def samples(job_id: int, owner: Owner):
    return ApiResponse.success(jobs.queue().report(job_id, owner)["samples"])


@router.post("/compare")
async def compare(body: SimCompareRequest, owner: Owner):
    a = jobs.queue().report(body.job_a, owner)
    b = jobs.queue().report(body.job_b, owner)
    return ApiResponse.success(compute.compare(a, b, body.threshold_pct))


@router.get("/presets")
async def presets():
    return ApiResponse.success({"scenarios": [
        {"name": "世界 BOSS 基准", "type": "world_boss", "rules": "active", "seed": 20261124,
         "runs": 10, "loadouts": [{"name": "无装备 40 级", "level": 40}],
         "targets": ["world_boss"], "params": {"max_rounds": 50}}]})
