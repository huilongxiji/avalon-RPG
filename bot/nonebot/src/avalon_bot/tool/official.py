from __future__ import annotations

from nonebot import get_driver, get_plugin_config
from nonebot.adapters import Event
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment
from nonebot.matcher import Matcher

from .at_user import AtUser
from .config import Config
from .segment import MessageSegmentPlus


def get_send_mode() -> str:
    mode = str(get_plugin_config(Config).game_send_mode).lower()
    return "text" if mode == "text" else "markdown"


def event_openid(event: object) -> str:
    value = getattr(event, "user_openid", None)
    if not value:
        raise RuntimeError("事件缺少 user_openid")
    return str(value)


def command_prefix() -> str:
    starts = get_driver().config.command_start
    prefixes = sorted((item for item in starts if item), key=lambda s: (s != '/', len(s), s))
    return prefixes[0] if prefixes else ""


def command_text(name: str, *, blank: bool = False) -> str:
    text = f"{command_prefix()}{name.strip()}"
    return f"{text} " if blank else text


def _is_private(event: Event) -> bool:
    return getattr(event, "message_type", "") == "private"


def _with_at_line(event: Event, content: str) -> str:
    """群聊且有 openid 时，正文前一行：头像｜艾特。私聊不加。"""
    openid = event_openid(event)
    if _is_private(event) or not openid:
        return content
    qq = event.get_user_id()
    avatar = f"![avatar#100px #100px](https://q1.qlogo.cn/g?b=qq&nk={qq}&s=100)"
    tag = AtUser.of(openid, private=False)
    if not tag:
        return content
    body = content.lstrip("\n")
    line = f"{avatar}｜{tag}"
    return f"{line}\n{body}" if body else line


def build_markdown(
    body: str,
    buttons: list[dict] | None = None,
) -> dict:
    data: dict = {
        "markdown": {"content": body},
        "keyboard": {"content": {"rows": []}},
    }
    if buttons:
        data["keyboard"]["content"]["rows"].append({"buttons": buttons})
    return data


async def reply_markdown(
    matcher: Matcher,
    event: Event,
    markdown: str,
    text: str | None = None,
) -> None:
    if get_send_mode() == "text":
        plain = text if text is not None else markdown
        if isinstance(event, MessageEvent):
            await matcher.finish(MessageSegment.reply(event.message_id) + plain)
        await matcher.finish(plain)
    segment = MessageSegmentPlus.markdown(
        _with_at_line(event, markdown),
        private=_is_private(event),
    )
    await matcher.finish(segment)
