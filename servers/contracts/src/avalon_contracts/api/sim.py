"""模拟接口格式。

模拟器只有一个可调参数：回合上限（最小 1，最大无限，默认 50，与 bot 一致）。
模拟不计保底。选"无限"时，连续 50 回合双方都没造成伤害判平局，防止死循环。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_MAX_ROUNDS = 50
ZERO_DAMAGE_STALL_ROUNDS = 50
UNLIMITED_WORDS = ("unlimited", "无限", "不限")


class SimModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SimParams(SimModel):
    # None 表示无限
    max_rounds: int | None = Field(default=DEFAULT_MAX_ROUNDS, ge=1, strict=True)

    @field_validator("max_rounds", mode="before")
    @classmethod
    def _parse_unlimited(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() in UNLIMITED_WORDS:
            return None
        return value

    @property
    def unlimited(self) -> bool:
        return self.max_rounds is None


class GearPiece(SimModel):
    item_id: int = Field(ge=0)
    enhance: int = Field(default=0, ge=0)
    temper: int = Field(default=0, ge=0)


class Loadout(SimModel):
    """一套配装：等级 + 各部位装备。"""

    level: int = Field(default=1, ge=1)
    gear: dict[str, GearPiece] = Field(default_factory=dict)
    name: str = Field(default="玩家", max_length=80)


class SimStatsRequest(SimModel):
    rules: str = "active"                # active / 版本号 / draft:<编号>
    loadout: Loadout


class SimBattleRequest(SimStatsRequest):
    target: str                          # 怪物代号，或 world_boss
    runs: int = Field(default=1, ge=1, le=100000)
    seed: int | None = None
    params: SimParams = Field(default_factory=SimParams)


JobType = Literal["batch", "matrix", "compare_gear", "dungeon", "tower", "world_boss", "enhance", "growth", "version_compare"]


class SimJobRequest(SimModel):
    type: JobType
    rules: str = "active"
    seed: int | None = None
    runs: int = Field(default=100, ge=1, le=100000)
    loadouts: list[Loadout] = Field(min_length=1, max_length=40)
    targets: list[str] = Field(default_factory=list, max_length=100)
    params: SimParams = Field(default_factory=SimParams)
    name: str = Field(default="", max_length=120)

    @model_validator(mode="after")
    def _budget(self) -> SimJobRequest:
        if self.runs * len(self.loadouts) * max(1, len(self.targets)) > 100000:
            raise ValueError("一个任务最多模拟 100000 场")
        if len(self.targets) != len(set(self.targets)):
            raise ValueError("对手不能重复")
        return self


JobStatus = Literal["queued", "running", "finished", "failed", "cancelled"]


class SimJobInfo(BaseModel):
    id: int
    type: JobType
    status: JobStatus
    progress: float = 0          # 0~1
    name: str = ""
    message: str = ""
    rules_version: int | None = None
    rules_digest: str = ""
    seed: int = 0
    completed: int = 0
    total: int = 0


class SimCompareRequest(SimModel):
    job_a: int = Field(gt=0)
    job_b: int = Field(gt=0)
    threshold_pct: float = Field(default=5, ge=0, allow_inf_nan=False)
