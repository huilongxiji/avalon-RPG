"""令牌工具：只保存哈希值，比对时用固定时间比较。"""

from __future__ import annotations

import hashlib
import hmac
import secrets


# 各服务令牌的权限：bot 只能调玩家接口；sim 只能调模拟接口（模拟器只跑模拟，不能改数据）。
# 管理接口（admin）只给网站管理员，M7 阶段接入登录。
SCOPES: dict[str, list[str]] = {"bot": ["player"], "sim": ["sim"]}


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def same_hash(token: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), stored_hash)


def new_token() -> str:
    return secrets.token_urlsafe(32)
