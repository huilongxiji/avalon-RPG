"""QQ 原生 Markdown 艾特。"""

from __future__ import annotations


class AtUser:
    """构造 <qqbot-at-user />。

    私聊(C2C) 不支持该标签，会直接 400；私聊请传 private=True。
    """

    __slots__ = ("openid", "private")

    def __init__(self, openid: str = "", *, private: bool = False) -> None:
        self.openid = openid or ""
        self.private = private

    def render(self) -> str:
        if self.private or not self.openid:
            return ""
        return f'<qqbot-at-user id="{self.openid}" />'

    def __str__(self) -> str:
        return self.render()

    @classmethod
    def of(cls, openid: str, *, private: bool = False) -> str:
        return cls(openid, private=private).render()
