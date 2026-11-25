"""NoneBot 2.5 公共依赖：调用者身份、命令及参数，不执行游戏业务。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Annotated

from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.matcher import Matcher
from nonebot.params import Command, CommandArg, Depends
from nonebot.permission import SUPERUSER

from .commands import BY_NAME
from .tool.official import command_prefix, event_openid
from .tool.permission import mentioned_openids


@dataclass(frozen=True)
class Caller:
    openid: str
    superuser: bool
    request_id: str
    session: str
    prefix: str


async def get_caller(bot: Bot, event: MessageEvent, matcher: Matcher) -> Caller:
    try:
        openid = event_openid(event)
    except RuntimeError:
        await matcher.finish('消息缺少玩家身份，请检查 goqbot 连接')
    event_id = f'{event.self_id}:{event.get_session_id()}:{event.message_id}'
    group = getattr(event, 'group_id', None)
    return Caller(openid, await SUPERUSER(bot, event), hashlib.sha256(event_id.encode()).hexdigest(),
                  f'group_{group}' if group else 'private', command_prefix())


CurrentCaller = Annotated[Caller, Depends(get_caller)]


@dataclass(frozen=True)
class GameCall:
    caller: Caller
    command: str
    arguments: str
    mentions: list[str] | None


async def get_game_call(bot: Bot, event: MessageEvent, matcher: Matcher, caller: CurrentCaller,
                        command: Annotated[tuple[str, ...], Command()],
                        args: Annotated[Message, CommandArg()]) -> GameCall:
    # Command() 已由框架去掉前缀，并保留实际触发的别名（例如“强化武器”）。
    raw = command[0]
    definition = BY_NAME[raw]
    mentions = await mentioned_openids(bot, event) if definition.admin else []
    if definition.admin and mentions == [] and any(
        s.type == 'at' and str(s.data.get('qq')) not in ('all', str(event.self_id)) for s in event.message
    ):
        await matcher.finish('无法识别被艾特的玩家，请改用 openid')
    text = args.extract_plain_text()
    if definition.admin and any(s.type == 'at' and str(s.data.get('qq')) == 'all' for s in event.message):
        text = '全服 ' + text
    return GameCall(caller, raw, text, mentions)
