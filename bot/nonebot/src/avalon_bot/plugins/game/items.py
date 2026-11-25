"""道具商城：每条命令独立声明响应器和处理函数。"""

from typing import Annotated

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.matcher import Matcher
from nonebot.params import Depends

from ...dependencies import GameCall, get_game_call
from .handlers import handle_command

use_prop = on_command(
    '使用', priority=10, block=True,
    state={'avalon_feature': '道具商城', 'avalon_command': '使用'},
)


@use_prop.handle()
async def handle_use_prop(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


craft_prop = on_command(
    '道具合成', priority=10, block=True,
    state={'avalon_feature': '道具商城', 'avalon_command': '道具合成'},
)


@craft_prop.handle()
async def handle_craft_prop(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


shop = on_command(
    '商城', priority=10, block=True,
    state={'avalon_feature': '道具商城', 'avalon_command': '商城'},
)


@shop.handle()
async def handle_shop(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


redeem = on_command(
    '兑换', priority=10, block=True,
    state={'avalon_feature': '道具商城', 'avalon_command': '兑换'},
)


@redeem.handle()
async def handle_redeem(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


redeem_help = on_command(
    '兑换码', priority=10, block=True,
    state={'avalon_feature': '道具商城', 'avalon_command': '兑换码'},
)


@redeem_help.handle()
async def handle_redeem_help(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)
