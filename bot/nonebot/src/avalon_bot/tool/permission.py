"""按钮权限与 openid 解析。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from nonebot.log import logger

from .constants import PermissionType

if TYPE_CHECKING:
    from nonebot.adapters.onebot.v11 import Bot, MessageEvent


class Permission:
    """构造 action.permission。

    type=0 时 specify_user_ids 须为 QQ openid。
    私聊(C2C) 对 type=0 偶发误报「无权限」，私聊建议 everyone()。
    """

    __slots__ = ("type", "specify_user_ids", "specify_role_ids")

    def __init__(
        self,
        permission_type: int | PermissionType = PermissionType.EVERYONE,
        *,
        specify_user_ids: Sequence[str] | None = None,
        specify_role_ids: Sequence[str] | None = None,
    ) -> None:
        self.type = int(permission_type)
        self.specify_user_ids = list(specify_user_ids or [])
        self.specify_role_ids = list(specify_role_ids or [])

    def to_dict(self) -> dict:
        out: dict = {"type": self.type}
        if self.specify_user_ids:
            out["specify_user_ids"] = self.specify_user_ids
        if self.specify_role_ids:
            out["specify_role_ids"] = self.specify_role_ids
        return out

    @classmethod
    def everyone(cls) -> "Permission":
        return cls(PermissionType.EVERYONE)

    @classmethod
    def admin(cls) -> "Permission":
        return cls(PermissionType.ADMIN)

    @classmethod
    def users(cls, *openids: str) -> "Permission":
        return cls(
            PermissionType.SPECIFY_USER,
            specify_user_ids=[x for x in openids if x],
        )

    @classmethod
    def owner(
        cls,
        openid: str | None,
        *,
        private: bool = False,
    ) -> "Permission":
        """群聊限本人；私聊改 everyone（避免 C2C 白名单误报）。"""
        if private or not openid:
            return cls.everyone()
        return cls.users(openid)


class OpenIdHelper:
    """通过 goqbot get_openid 反查用户 openid。"""

    @staticmethod
    async def from_user_id(bot: "Bot", user_id: int) -> str | None:
        try:
            ret = await bot.call_api("get_openid", user_id=user_id)
        except Exception as e:
            logger.warning(f"[tool] get_openid 失败: {e}")
            return None
        if isinstance(ret, dict):
            return ret.get("user_openid") or None
        return None


async def mentioned_openids(bot: "Bot", event: "MessageEvent") -> list[str] | None:
    """从艾特段的 qq 反查 user_openid。没有艾特任何人时返回 None。"""
    openids: list[str] = []
    seen: set[str] = set()
    mentioned = False
    for seg in event.get_message():
        if seg.type != "at":
            continue
        qq = str(seg.data.get("qq") or "")
        if qq in ("", "all") or qq == str(event.self_id):
            continue
        mentioned = True
        if not qq.isdigit():
            continue
        found = await OpenIdHelper.from_user_id(bot, int(qq))
        openid = found or ""
        if not openid or openid in seen:
            continue
        seen.add(openid)
        openids.append(openid)
    if not mentioned:
        return None
    return openids
