"""Markdown 正文「指令蓝字」（mqqapi://aio/inlinecmd）。"""

from __future__ import annotations

from urllib.parse import quote


class BlueLink:
    """把文字变成 QQ markdown 指令蓝字。

    enter=true 回车直发仅私聊(C2C)有效；群聊只会填入输入框。
    """

    __slots__ = ("command", "enter", "reply", "label")

    def __init__(
        self,
        command: str,
        *,
        enter: bool = False,
        reply: bool = False,
        label: str | None = None,
    ) -> None:
        self.command = command
        self.enter = bool(enter)
        self.reply = bool(reply)
        self.label = label if label is not None else command

    def render(self) -> str:
        cmd = quote(self.command, safe="")
        return (
            f"[{self.label}](mqqapi://aio/inlinecmd?"
            f"command={cmd}"
            f"&enter={str(self.enter).lower()}"
            f"&reply={str(self.reply).lower()})"
        )

    def __str__(self) -> str:
        return self.render()

    @classmethod
    def fill(cls, command: str, *, label: str | None = None) -> "BlueLink":
        return cls(command, enter=False, reply=False, label=label)

    @classmethod
    def send(cls, command: str, *, label: str | None = None) -> "BlueLink":
        """点击后直接发送（仅私聊有效）。"""
        return cls(command, enter=True, reply=False, label=label)

    @classmethod
    def fill_reply(cls, command: str, *, label: str | None = None) -> "BlueLink":
        return cls(command, enter=False, reply=True, label=label)

    @classmethod
    def url(
        cls,
        command: str,
        *,
        enter: bool = False,
        reply: bool = False,
    ) -> str:
        """只返回 mqqapi URL（无 markdown 外壳）。"""
        cmd = quote(command, safe="")
        return (
            f"mqqapi://aio/inlinecmd?"
            f"command={cmd}"
            f"&enter={str(enter).lower()}"
            f"&reply={str(reply).lower()}"
        )
