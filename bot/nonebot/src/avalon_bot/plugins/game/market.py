"""市场交易：每条命令独立声明响应器和处理函数。"""

from typing import Annotated

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.matcher import Matcher
from nonebot.params import Depends

from ...dependencies import GameCall, get_game_call
from .handlers import handle_command

market = on_command(
    '市场', priority=10, block=True,
    state={'avalon_feature': '市场交易', 'avalon_command': '市场'},
)


@market.handle()
async def handle_market(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


listing_detail = on_command(
    '详情', priority=10, block=True,
    state={'avalon_feature': '市场交易', 'avalon_command': '详情'},
)


@listing_detail.handle()
async def handle_listing_detail(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


create_listing = on_command(
    '上架', priority=10, block=True,
    state={'avalon_feature': '市场交易', 'avalon_command': '上架'},
)


@create_listing.handle()
async def handle_create_listing(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


buy = on_command(
    '购买', priority=10, block=True,
    state={'avalon_feature': '市场交易', 'avalon_command': '购买'},
)


@buy.handle()
async def handle_buy(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


cancel_listing = on_command(
    '下架', priority=10, block=True,
    state={'avalon_feature': '市场交易', 'avalon_command': '下架'},
)


@cancel_listing.handle()
async def handle_cancel_listing(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)
