"""背包装备：每条命令独立声明响应器和处理函数。"""

from typing import Annotated

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.matcher import Matcher
from nonebot.params import Depends

from ...dependencies import GameCall, get_game_call
from .handlers import handle_command

bag = on_command(
    '背包', priority=10, block=True,
    state={'avalon_feature': '背包装备', 'avalon_command': '背包'},
)


@bag.handle()
async def handle_bag(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


sort_bag = on_command(
    '整理背包', priority=10, block=True,
    state={'avalon_feature': '背包装备', 'avalon_command': '整理背包'},
)


@sort_bag.handle()
async def handle_sort_bag(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


view_equipped = on_command(
    '查看', aliases={'查看武器', '查看护甲', '查看手镯', '查看项链', '查看宝石'}, priority=10, block=True,
    state={'avalon_feature': '背包装备', 'avalon_command': '查看'},
)


@view_equipped.handle()
async def handle_view_equipped(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


bag_detail = on_command(
    '装备详情', priority=10, block=True,
    state={'avalon_feature': '背包装备', 'avalon_command': '装备详情'},
)


@bag_detail.handle()
async def handle_bag_detail(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


equip = on_command(
    '装备', priority=10, block=True,
    state={'avalon_feature': '背包装备', 'avalon_command': '装备'},
)


@equip.handle()
async def handle_equip(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


unequip = on_command(
    '卸下', priority=10, block=True,
    state={'avalon_feature': '背包装备', 'avalon_command': '卸下'},
)


@unequip.handle()
async def handle_unequip(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


enhance = on_command(
    '强化', aliases={'强化武器', '强化护甲', '强化手镯', '强化项链'}, priority=10, block=True,
    state={'avalon_feature': '背包装备', 'avalon_command': '强化'},
)


@enhance.handle()
async def handle_enhance(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


temper = on_command(
    '淬炼', aliases={'淬炼武器', '淬炼护甲', '淬炼手镯', '淬炼项链'}, priority=10, block=True,
    state={'avalon_feature': '背包装备', 'avalon_command': '淬炼'},
)


@temper.handle()
async def handle_temper(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


sell = on_command(
    '出售', priority=10, block=True,
    state={'avalon_feature': '背包装备', 'avalon_command': '出售'},
)


@sell.handle()
async def handle_sell(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


sell_many = on_command(
    '批量出售', priority=10, block=True,
    state={'avalon_feature': '背包装备', 'avalon_command': '批量出售'},
)


@sell_many.handle()
async def handle_sell_many(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


decompose = on_command(
    '分解', priority=10, block=True,
    state={'avalon_feature': '背包装备', 'avalon_command': '分解'},
)


@decompose.handle()
async def handle_decompose(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


expand_bag = on_command(
    '背包扩容', priority=10, block=True,
    state={'avalon_feature': '背包装备', 'avalon_command': '背包扩容'},
)


@expand_bag.handle()
async def handle_expand_bag(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


craft = on_command(
    '合成', priority=10, block=True,
    state={'avalon_feature': '背包装备', 'avalon_command': '合成'},
)


@craft.handle()
async def handle_craft(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


warehouse = on_command(
    '仓库', priority=10, block=True,
    state={'avalon_feature': '背包装备', 'avalon_command': '仓库'},
)


@warehouse.handle()
async def handle_warehouse(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)
