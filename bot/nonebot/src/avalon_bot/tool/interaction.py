"""互动事件字段读取（goqbot 附加字段）。"""

from __future__ import annotations

from typing import Any


class Interaction:
    """从 notice/message 上取 interaction_id / button_data 等。"""

    @staticmethod
    def field(event: object, name: str) -> Any:
        if hasattr(event, name):
            val = getattr(event, name)
            if val not in (None, ""):
                return val
        extra = getattr(event, "__dict__", {}) or {}
        if name in extra and extra[name] not in (None, ""):
            return extra[name]
        # v2 只调用 model_dump；缺字段时不能再调用已弃用的 dict()。
        # 保留 v1 事件兼容，但两套接口只择一使用。
        dump = getattr(event, 'model_dump', None) or getattr(event, 'dict', None)
        if callable(dump):
            data = dump()
            if isinstance(data, dict) and data.get(name) not in (None, ""):
                return data[name]
        return None

    @classmethod
    def button_data(cls, event: object) -> str | None:
        val = cls.field(event, "button_data")
        return str(val) if val is not None else None

    @classmethod
    def interaction_id(cls, event: object) -> str | None:
        val = cls.field(event, "interaction_id")
        return str(val) if val is not None else None
