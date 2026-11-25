"""规则快照：激活时把整个规则版本编译好放在内存里，之后的请求直接读内存。

切换是原子的：只替换一个引用。正在进行的战斗继续用开始时拿到的旧快照打完。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping

from .expr import CompiledExpr


@dataclass(frozen=True)
class RuleSnapshot:
    version_id: int | None
    built_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    formulas: Mapping[str, CompiledExpr] = field(default_factory=lambda: MappingProxyType({}))
    settings: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    # 以下在 M2/M3 阶段填充：属性定义、层数定义、效果、装备、套装、怪物、副本……
    data: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    @property
    def empty(self) -> bool:
        return self.version_id is None


class SnapshotHolder:
    """全局只有一个；get() 拿当前快照，swap() 原子切换。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current = RuleSnapshot(version_id=None)

    def get(self) -> RuleSnapshot:
        return self._current

    def swap(self, snapshot: RuleSnapshot) -> RuleSnapshot:
        with self._lock:
            previous = self._current
            self._current = snapshot
            return previous


holder = SnapshotHolder()
