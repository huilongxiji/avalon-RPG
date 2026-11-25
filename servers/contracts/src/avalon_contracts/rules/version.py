"""规则版本。每个版本是公式、效果、装备、怪物……在某一时刻的整体快照。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

VersionStatus = Literal["draft", "active", "archived", "discarded"]

STATUS_LABELS = {"draft": "草稿", "active": "生效中", "archived": "已归档", "discarded": "已放弃"}


class RuleVersionInfo(BaseModel):
    id: int
    parent_id: int | None = None
    status: VersionStatus
    note: str = ""
    created_by: str = ""
    created_at: datetime | None = None
    activated_at: datetime | None = None


class DraftCreate(BaseModel):
    """新建草稿：从 parent_id（不填则为当前生效版本）整份复制。"""

    parent_id: int | None = None
    note: str = ""


class RulesRef(BaseModel):
    """接口里指定规则版本的写法：active（当前生效）、具体版本号、或 draft:<编号>。"""

    ref: str = "active"

    def version_id(self) -> int | None:
        """返回具体版本号；active 返回 None（由后端解析为当前生效版本）。"""
        text = self.ref.strip()
        if text == "active":
            return None
        if text.startswith("draft:"):
            text = text.split(":", 1)[1]
        return int(text)


class DraftState(BaseModel):
    """网站顶部草稿条：当前生效版本、正在编辑的草稿（同一时间只有一个草稿）。"""

    active: RuleVersionInfo | None = None
    draft: RuleVersionInfo | None = None
    changes: int = 0                     # 草稿和它的上一个版本相比改了几处
    editable: bool = False               # 这次请求能不能修改（只有在运行网站的这台电脑上打开才能改）


class DiffEntry(BaseModel):
    category: str                        # items / formulas / sets ……
    category_label: str                  # 装备 / 公式 / 套装 ……
    key: str
    name: str
    change: Literal["added", "removed", "changed"]
    details: list[str] = []              # 改了哪些地方，例如"攻击：100 → 120"


class ValidateResult(BaseModel):
    ok: bool
    problems: list[str] = []
    battles: int = 0                     # 自检打了几场
