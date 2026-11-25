"""api.db 的模型：网站账号、令牌、审计。令牌只存哈希值，不存原文。"""

from __future__ import annotations

from tortoise import fields
from tortoise.models import Model


class AdminUser(Model):
    id = fields.IntField(primary_key=True)
    username = fields.CharField(max_length=64, unique=True)
    password_hash = fields.CharField(max_length=256)
    role = fields.CharField(max_length=16, default="viewer")  # viewer / editor / admin / super
    disabled = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    last_login_at = fields.DatetimeField(null=True)

    class Meta:
        table = "admin_users"


class WebSession(Model):
    """网站会话：只存令牌哈希；账号由 SQL 手动入库，运行时不创建账号。"""

    id = fields.IntField(primary_key=True)
    user = fields.ForeignKeyField("api.AdminUser", related_name="sessions", on_delete=fields.CASCADE)
    token_hash = fields.CharField(max_length=64, unique=True)
    credential_version = fields.CharField(max_length=64)
    expires_at = fields.DatetimeField(db_index=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "web_sessions"


class ServiceToken(Model):
    """服务令牌：bot 前端、模拟器调用 API 时使用。"""

    id = fields.IntField(primary_key=True)
    name = fields.CharField(max_length=64, unique=True)
    token_hash = fields.CharField(max_length=64, unique=True)
    scopes = fields.JSONField(default=list)          # 例如 ["player", "sim"]
    revoked = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "service_tokens"


class FeedToken(Model):
    """数据源令牌：本地 Excel 读取实时数据用，只读，可以随时作废。"""

    id = fields.IntField(primary_key=True)
    owner = fields.CharField(max_length=64)
    token_hash = fields.CharField(max_length=64, unique=True)
    note = fields.CharField(max_length=128, default="")
    revoked = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "feed_tokens"


class PlayerToken(Model):
    """预留：以后安卓软件的玩家登录令牌（本期不实现）。"""

    id = fields.IntField(primary_key=True)
    openid = fields.CharField(max_length=64, db_index=True)
    token_hash = fields.CharField(max_length=64, unique=True)
    expires_at = fields.DatetimeField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "player_tokens"


class AuditLog(Model):
    """管理操作审计：只追加，不修改。"""

    id = fields.BigIntField(primary_key=True)
    at = fields.DatetimeField(auto_now_add=True, db_index=True)
    actor = fields.CharField(max_length=64)
    action = fields.CharField(max_length=64)
    target = fields.CharField(max_length=256, default="")
    detail = fields.JSONField(default=dict)
    ip = fields.CharField(max_length=64, default="")

    class Meta:
        table = "audit_log"
