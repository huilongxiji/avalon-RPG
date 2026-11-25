"""统一返回格式、分页、健康检查。

所有接口都返回 ``{"ok": true, "data": ...}`` 或
``{"ok": false, "error": {"code": ..., "message": ..., "detail": {...}}}``。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

from .errors import message_of

T = TypeVar("T")


class ApiError(BaseModel):
    code: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ApiResponse(BaseModel, Generic[T]):
    ok: bool = True
    data: T | None = None
    error: ApiError | None = None

    @classmethod
    def success(cls, data: T | None = None) -> "ApiResponse[T]":
        return cls(ok=True, data=data)

    @classmethod
    def failure(cls, code: str, message: str | None = None, **detail: Any) -> "ApiResponse[T]":
        return cls(ok=False, error=ApiError(code=code, message=message or message_of(code), detail=detail))


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 50


class Health(BaseModel):
    """各服务 /health 的统一返回。"""

    service: str
    ok: bool = True
    version: str = ""
    started_at: datetime | None = None
    # 当前生效的规则版本号（逻辑后端填写）
    rules_version: int | None = None
    # 附加信息，例如 bot 前端报告的 goqbot 连接数
    extra: dict[str, Any] = Field(default_factory=dict)
