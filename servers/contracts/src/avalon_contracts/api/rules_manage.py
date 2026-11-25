"""网站完整规则管理契约；保存时携带草稿编号和原记录摘要。"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RuleCategory = Literal["effects", "sets", "monsters", "dungeons", "drops", "props", "recipes", "prop_recipes", "stacks"]


class RuleWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_id: int = Field(gt=0)
    before_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    data: dict[str, Any]


class RuleDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_id: int = Field(gt=0)
    before_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class RuleRecord(BaseModel):
    key: str
    name: str
    summary: str = ""
    data: dict[str, Any]
    hash: str
    references: list[str] = Field(default_factory=list)
    protected_reason: str = ""


class RuleRecords(BaseModel):
    version_id: int
    draft: bool
    records: list[RuleRecord]

