"""Keyboard 单个按钮构造。"""

from __future__ import annotations

from typing import Any

from .constants import DEFAULT_UNSUPPORT_TIPS, ActionType, Style
from .modal import Modal
from .permission import Permission


class Button:
    """构造单个 Keyboard 按钮 dict。"""

    __slots__ = (
        "id",
        "label",
        "visited_label",
        "style",
        "action_type",
        "data",
        "permission",
        "modal",
        "group_id",
        "enter",
        "reply",
        "anchor",
        "unsupport_tips",
        "click_limit",
    )

    def __init__(
        self,
        *,
        label: str,
        data: str,
        action_type: int | ActionType,
        btn_id: str | None = None,
        visited_label: str | None = None,
        style: int | Style = Style.BLUE,
        permission: Permission | dict | None = None,
        modal: Modal | dict | None = None,
        group_id: str | None = None,
        enter: bool | None = None,
        reply: bool | None = None,
        anchor: int | None = None,
        unsupport_tips: str | None = DEFAULT_UNSUPPORT_TIPS,
        click_limit: int | None = None,
    ) -> None:
        self.id = btn_id
        self.label = label
        self.visited_label = visited_label if visited_label is not None else label
        self.style = int(style)
        self.action_type = int(action_type)
        self.data = data
        self.permission = permission
        self.modal = modal
        self.group_id = group_id
        self.enter = enter
        self.reply = reply
        self.anchor = anchor
        self.unsupport_tips = unsupport_tips
        self.click_limit = click_limit

    def _permission_dict(self) -> dict:
        if self.permission is None:
            return Permission.everyone().to_dict()
        if isinstance(self.permission, Permission):
            return self.permission.to_dict()
        return dict(self.permission)

    def _modal_dict(self) -> dict | None:
        if self.modal is None:
            return None
        if isinstance(self.modal, Modal):
            return self.modal.to_dict()
        return dict(self.modal)

    def to_dict(self) -> dict:
        action: dict[str, Any] = {
            "type": self.action_type,
            "data": self.data,
            "permission": self._permission_dict(),
        }
        if self.unsupport_tips is not None:
            action["unsupport_tips"] = self.unsupport_tips
        if self.click_limit is not None:
            action["click_limit"] = self.click_limit

        if self.action_type == ActionType.COMMAND:
            if self.enter is not None:
                action["enter"] = bool(self.enter)
            if self.reply is not None:
                action["reply"] = bool(self.reply)
            if self.anchor is not None:
                action["anchor"] = self.anchor
        elif self.anchor is not None:
            action["anchor"] = self.anchor

        modal = self._modal_dict()
        if modal:
            action["modal"] = modal

        btn: dict[str, Any] = {
            "render_data": {
                "label": self.label,
                "visited_label": self.visited_label,
                "style": self.style,
            },
            "action": action,
        }
        if self.id:
            btn["id"] = self.id
        if self.group_id and self.action_type == ActionType.CALLBACK:
            btn["group_id"] = self.group_id
        return btn

    @classmethod
    def url(
        cls,
        url: str,
        label: str,
        *,
        btn_id: str | None = None,
        visited_label: str | None = None,
        style: int | Style = Style.BLUE,
        permission: Permission | dict | None = None,
        **kwargs,
    ) -> "Button":
        return cls(
            label=label,
            data=url,
            action_type=ActionType.URL,
            btn_id=btn_id,
            visited_label=visited_label,
            style=style,
            permission=permission,
            **kwargs,
        )

    @classmethod
    def callback(
        cls,
        data: str,
        label: str,
        *,
        btn_id: str | None = None,
        visited_label: str | None = None,
        style: int | Style = Style.BLUE,
        permission: Permission | dict | None = None,
        modal: Modal | dict | None = None,
        group_id: str | None = None,
        **kwargs,
    ) -> "Button":
        return cls(
            label=label,
            data=data,
            action_type=ActionType.CALLBACK,
            btn_id=btn_id,
            visited_label=visited_label,
            style=style,
            permission=permission,
            modal=modal,
            group_id=group_id,
            **kwargs,
        )

    @classmethod
    def command(
        cls,
        command: str,
        label: str,
        *,
        btn_id: str | None = None,
        visited_label: str | None = None,
        style: int | Style = Style.BLUE,
        permission: Permission | dict | None = None,
        enter: bool | None = False,
        reply: bool | None = False,
        anchor: int | None = None,
        **kwargs,
    ) -> "Button":
        """指令按钮。anchor=1 时唤起手机端相册（仅单聊）。"""
        return cls(
            label=label,
            data=command,
            action_type=ActionType.COMMAND,
            btn_id=btn_id,
            visited_label=visited_label,
            style=style,
            permission=permission,
            enter=enter,
            reply=reply,
            anchor=anchor,
            **kwargs,
        )

    @classmethod
    def album(
        cls,
        command: str,
        label: str = "上传图片",
        *,
        btn_id: str | None = None,
        permission: Permission | dict | None = None,
        **kwargs,
    ) -> "Button":
        """私聊唤起相册选图器（anchor=1）。"""
        return cls.command(
            command,
            label,
            btn_id=btn_id,
            permission=permission,
            anchor=1,
            enter=False,
            **kwargs,
        )


async def build_buttons_json(
    data: str,
    label: str = "按钮",
    action_type: int = 0,
    permission_type: int = 2,
    specify_user_ids: list | None = None,
    anchor: int | None = None,
    unsupport_tips: str | None = None,
) -> dict:
    """构造键盘按钮。action_type：0=URL 1=回调 2=指令。permission_type：2=所有人。"""
    btn = {
        "render_data": {"label": label, "style": 1},
        "action": {
            "type": action_type,
            "data": data,
            "permission": {"type": permission_type},
        },
    }
    if specify_user_ids is not None and permission_type == 0:
        btn["action"]["permission"]["specify_user_ids"] = specify_user_ids
    if anchor is not None:
        btn["action"]["anchor"] = anchor
    if unsupport_tips is not None:
        btn["action"]["unsupport_tips"] = unsupport_tips
    return btn
