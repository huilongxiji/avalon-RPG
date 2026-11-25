"""帮助菜单：每条命令独立声明响应器和处理函数。"""

from typing import Annotated

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.matcher import Matcher
from nonebot.params import Depends

from ...dependencies import GameCall, get_game_call
from .handlers import handle_command

help_menu = on_command(
    '帮助', aliases={'菜单', 'help'}, priority=10, block=True,
    state={'avalon_feature': '帮助菜单', 'avalon_command': '帮助'},
)


@help_menu.handle()
async def handle_help_menu(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


bag_menu = on_command(
    '背包菜单', priority=10, block=True,
    state={'avalon_feature': '帮助菜单', 'avalon_command': '背包菜单'},
)


@bag_menu.handle()
async def handle_bag_menu(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)
