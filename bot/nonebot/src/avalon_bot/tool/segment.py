"""MessageSegmentPlus — MessageSegment 的 Markdown 扩展（纯构造，不发送）。"""

from __future__ import annotations

import json
from typing import Any

from nonebot.adapters.onebot.v11 import MessageSegment
from typing_extensions import Self

from .at_user import AtUser
from .button import Button
from .keyboard import Keyboard


def _prepend_at(content: str, at: str | None, private: bool) -> str:
    if not at:
        return content
    tag = AtUser.of(at, private=private)
    if not tag:
        return content
    body = content.lstrip("\n")
    return f"{tag}\n{body}" if body else tag


def _build_payload(
    markdown: dict,
    keyboard: Keyboard | dict | list | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"markdown": markdown}
    kb = Keyboard.normalize(keyboard)
    if kb is not None:
        payload["keyboard"] = kb
    return payload


class MessageSegmentPlus(MessageSegment):
    """QQ 官方 Markdown 消息段扩展。

    用法与普通 NoneBot 一致::

        await matcher.finish(MessageSegmentPlus.markdown("### 标题"))
        await matcher.send(MessageSegmentPlus.markdown(
            "正文", at=openid, private=private, keyboard=kb,
        ))

    本类只构造 MessageSegment，不负责发送。
    按钮须先用 Button / Keyboard 构建后再传入。
    """

    @classmethod
    def _make(cls, payload: dict[str, Any], *, as_json: bool = True) -> Self:
        data: Any = json.dumps(payload, ensure_ascii=False) if as_json else payload
        return cls("markdown", {"data": data})

    @classmethod
    def markdown(
        cls,
        content: str,
        /,
        *,
        at: str | None = None,
        private: bool = False,
        keyboard: Keyboard | dict | list | None = None,
        as_json: bool = True,
    ) -> Self:
        """原生 markdown。content 为位置参数；可选 at / keyboard。"""
        text = _prepend_at(content, at, private)
        return cls._make(
            _build_payload({"content": text}, keyboard),
            as_json=as_json,
        )

    @classmethod
    def markdown_with_keyboard(
        cls,
        content: str,
        keyboard: Keyboard | dict | list,
        /,
        *,
        at: str | None = None,
        private: bool = False,
        as_json: bool = True,
    ) -> Self:
        """原生 markdown + 键盘（keyboard 必填）。"""
        return cls.markdown(
            content,
            at=at,
            private=private,
            keyboard=keyboard,
            as_json=as_json,
        )

    @classmethod
    def markdown_raw(
        cls,
        payload: dict[str, Any],
        /,
        *,
        as_json: bool = True,
    ) -> Self:
        """直接传入完整 payload（markdown / keyboard）。"""
        return cls._make(payload, as_json=as_json)


__all__ = ["MessageSegmentPlus", "Button", "Keyboard"]
