"""战斗战报：每条命令独立声明响应器和处理函数。"""

from typing import Annotated

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.matcher import Matcher
from nonebot.params import Depends

from ...dependencies import GameCall, get_game_call
from .handlers import handle_command

dungeon = on_command(
    '副本', priority=10, block=True,
    state={'avalon_feature': '战斗战报', 'avalon_command': '副本'},
)


@dungeon.handle()
async def handle_dungeon(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


dungeon_guide = on_command(
    '副本图鉴', priority=10, block=True,
    state={'avalon_feature': '战斗战报', 'avalon_command': '副本图鉴'},
)


@dungeon_guide.handle()
async def handle_dungeon_guide(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


battle_detail = on_command(
    '战报详情', priority=10, block=True,
    state={'avalon_feature': '战斗战报', 'avalon_command': '战报详情'},
)


@battle_detail.handle()
async def handle_battle_detail(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


tower = on_command(
    '爬塔', priority=10, block=True,
    state={'avalon_feature': '战斗战报', 'avalon_command': '爬塔'},
)


@tower.handle()
async def handle_tower(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


tower_summary = on_command(
    '爬塔概括', priority=10, block=True,
    state={'avalon_feature': '战斗战报', 'avalon_command': '爬塔概括'},
)


@tower_summary.handle()
async def handle_tower_summary(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


tower_detail = on_command(
    '爬塔详情', priority=10, block=True,
    state={'avalon_feature': '战斗战报', 'avalon_command': '爬塔详情'},
)


@tower_detail.handle()
async def handle_tower_detail(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


world_boss = on_command(
    '世界BOSS', aliases={'世界boss'}, priority=10, block=True,
    state={'avalon_feature': '战斗战报', 'avalon_command': '世界BOSS'},
)


@world_boss.handle()
async def handle_world_boss(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


world_rank = on_command(
    '世界排行榜', priority=10, block=True,
    state={'avalon_feature': '战斗战报', 'avalon_command': '世界排行榜'},
)


@world_rank.handle()
async def handle_world_rank(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)
