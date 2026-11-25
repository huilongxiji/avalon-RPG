"""网站登录及现有账号管理。无注册、创建账号或初始化管理员接口。"""

from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from avalon_contracts.common import ApiResponse
from avalon_contracts.errors import GameError
from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints, field_validator
from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from ...auth.passwords import hash_password, validate_password, verify_password
from ...auth.tokens import hash_token, new_token
from ...auth.web import (
    COOKIE_NAME,
    ROLES,
    SESSION_SECONDS,
    check_origin,
    credential_version,
    csrf_token,
    current_user,
    login_limiter,
    require_role,
)
from ...config import get_settings
from ...store.models import AdminUser, AuditLog, WebSession

router = APIRouter(prefix="/api/v1", tags=["网站账号"])
Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Role = Literal["viewer", "editor", "admin", "super"]
_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: Username
    password: SecretStr = Field(min_length=1, max_length=128)


class NewPassword(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: SecretStr = Field(min_length=12, max_length=128)

    @field_validator("password")
    @classmethod
    def valid_password(cls, value: SecretStr) -> SecretStr:
        validate_password(value.get_secret_value())
        return value


class ChangePassword(NewPassword):
    current_password: SecretStr = Field(min_length=1, max_length=128)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role
    disabled: bool


def user_data(user: AdminUser) -> dict:
    return {"id": user.id, "username": user.username, "role": user.role, "disabled": user.disabled,
            "created_at": user.created_at.isoformat(),
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None}


def _ip(request: Request) -> str:
    return request.client.host[:64] if request.client else ""


async def audit(request: Request, actor: AdminUser, action: str, target: AdminUser, **detail) -> None:
    # 不记录密码、哈希、Cookie、CSRF 或请求体。
    await AuditLog.create(actor=actor.username, action=action, target=f"website-user:{target.id}",
                          detail=detail, ip=_ip(request))


@router.post("/auth/login")
async def login(body: LoginBody, request: Request, response: Response):
    check_origin(request)
    if request.headers.get("x-avalon-client") != "web":
        raise GameError("forbidden", "请从网站登录页面提交")
    login_limiter.check(body.username, _ip(request))
    user = await AdminUser.get_or_none(username=body.username)
    valid = await asyncio.to_thread(verify_password, body.password.get_secret_value(),
                                    user.password_hash if user else _DUMMY_HASH)
    if not valid or user is None or user.disabled or user.role not in ROLES:
        raise GameError("unauthorized", "账号或密码不正确，或账号不可用")
    now = datetime.now(timezone.utc)
    token = new_token()
    async with in_transaction("api"):
        # 验证密码期间可能被管理员禁用、重置或通过 SQL 修改。
        fresh = await AdminUser.get_or_none(id=user.id)
        if fresh is None or fresh.disabled or credential_version(fresh) != credential_version(user):
            raise GameError("unauthorized", "账号状态已改变，请重新登录")
        await WebSession.filter(Q(expires_at__lte=now) | Q(token_hash=hash_token(request.cookies.get(COOKIE_NAME, "")))).delete()
        await WebSession.create(user=fresh, token_hash=hash_token(token),
                                credential_version=credential_version(fresh),
                                expires_at=now + timedelta(seconds=SESSION_SECONDS))
        fresh.last_login_at = now
        await fresh.save(update_fields=["last_login_at"])
        await audit(request, fresh, "website.login", fresh)
    login_limiter.success(body.username)
    response.set_cookie(COOKIE_NAME, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=get_settings().web_cookie_secure or request.url.scheme == "https",
                        samesite="lax", path="/")
    return ApiResponse.success({"user": user_data(fresh), "csrf_token": csrf_token(token)})


@router.get("/auth/me")
async def me(request: Request, user: Annotated[AdminUser, Depends(current_user)]):
    return ApiResponse.success({"user": user_data(user), "csrf_token": csrf_token(request.cookies[COOKIE_NAME])})


@router.post("/auth/logout")
async def logout(request: Request, response: Response, user: Annotated[AdminUser, Depends(current_user)]):
    await WebSession.filter(token_hash=hash_token(request.cookies[COOKIE_NAME])).delete()
    response.delete_cookie(COOKIE_NAME, path="/")
    await audit(request, user, "website.logout", user)
    return ApiResponse.success(None)


@router.put("/auth/password")
async def change_password(body: ChangePassword, request: Request, response: Response,
                          user: Annotated[AdminUser, Depends(current_user)]):
    if not await asyncio.to_thread(verify_password, body.current_password.get_secret_value(), user.password_hash):
        raise GameError("invalid", "当前密码不正确")
    encoded = await asyncio.to_thread(hash_password, body.password.get_secret_value())
    async with in_transaction("api"):
        count = await AdminUser.filter(id=user.id, password_hash=user.password_hash, disabled=False).update(password_hash=encoded)
        if count != 1:
            raise GameError("unauthorized", "账号状态已改变，请重新登录")
        await WebSession.filter(user_id=user.id).delete()
        await audit(request, user, "website.password.change", user)
    response.delete_cookie(COOKIE_NAME, path="/")
    return ApiResponse.success(None)


@router.get("/admin/users")
async def users(actor: Annotated[AdminUser, Depends(require_role("super"))], q: str = Query(default="", max_length=64), page: int = Query(default=1, ge=1),
                size: int = Query(default=20, ge=1, le=100), role: Role | None = None,
                disabled: bool | None = None):
    query = AdminUser.all()
    if q.strip():
        query = query.filter(username__icontains=q.strip())
    if role is not None:
        query = query.filter(role=role)
    if disabled is not None:
        query = query.filter(disabled=disabled)
    total = await query.count()
    rows = await query.order_by("id").offset((page - 1) * size).limit(size)
    return ApiResponse.success({"items": [user_data(row) for row in rows], "total": total, "page": page, "size": size})


async def _account_for_update(user_id: int, actor: AdminUser) -> AdminUser:
    # 事务内再校验操作者，避免并发撤权后仍能写入。
    fresh_actor = await AdminUser.get_or_none(id=actor.id, disabled=False, role="super")
    if fresh_actor is None or credential_version(fresh_actor) != credential_version(actor):
        raise GameError("unauthorized", "账号权限已改变，请重新登录")
    target = await AdminUser.get_or_none(id=user_id)
    if target is None:
        raise GameError("website_user_not_found", "网站账号不存在")
    return target


@router.patch("/admin/users/{user_id}")
async def update_user(user_id: int, body: UserUpdate, request: Request,
                      actor: Annotated[AdminUser, Depends(require_role("super"))]):
    async with in_transaction("api"):
        target = await _account_for_update(user_id, actor)
        if target.id == actor.id and (body.disabled or body.role != "super"):
            raise GameError("conflict", "不能禁用自己或降低自己的权限")
        if target.role == "super" and not target.disabled and (body.disabled or body.role != "super"):
            if await AdminUser.filter(role="super", disabled=False).count() <= 1:
                raise GameError("conflict", "必须保留至少一个可用的超级管理员")
        before = {"role": target.role, "disabled": target.disabled}
        target.role, target.disabled = body.role, body.disabled
        await target.save(update_fields=["role", "disabled"])
        if before != body.model_dump():
            await WebSession.filter(user_id=target.id).delete()
            await audit(request, actor, "website.user.update", target, before=before, after=body.model_dump())
    return ApiResponse.success(user_data(target))


@router.put("/admin/users/{user_id}/password")
async def reset_password(user_id: int, body: NewPassword, request: Request,
                         actor: Annotated[AdminUser, Depends(require_role("super"))]):
    if user_id == actor.id:
        raise GameError("conflict", "请使用右上角的修改密码功能修改自己的密码")
    encoded = await asyncio.to_thread(hash_password, body.password.get_secret_value())
    async with in_transaction("api"):
        target = await _account_for_update(user_id, actor)
        target.password_hash = encoded
        await target.save(update_fields=["password_hash"])
        await WebSession.filter(user_id=target.id).delete()
        await audit(request, actor, "website.password.reset", target)
    return ApiResponse.success(None)
