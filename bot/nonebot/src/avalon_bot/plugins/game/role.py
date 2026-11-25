"""角色：每条命令独立声明响应器和处理函数。"""

from typing import Annotated

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.matcher import Matcher
from nonebot.params import Depends

from ...dependencies import GameCall, get_game_call
from .handlers import handle_command

checkin = on_command(
    '签到', aliases={'打卡'}, priority=10, block=True,
    state={'avalon_feature': '角色', 'avalon_command': '签到'},
)


@checkin.handle()
async def handle_checkin(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


panel = on_command(
    '面板', priority=10, block=True,
    state={'avalon_feature': '角色', 'avalon_command': '面板'},
)


@panel.handle()
async def handle_panel(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


profile = on_command(
    '个人信息', priority=10, block=True,
    state={'avalon_feature': '角色', 'avalon_command': '个人信息'},
)


@profile.handle()
async def handle_profile(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)
