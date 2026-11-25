"""管理员：每条命令独立声明响应器和处理函数。"""

from typing import Annotated

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.matcher import Matcher
from nonebot.params import Depends
from nonebot.permission import SUPERUSER

from ...dependencies import GameCall, get_game_call
from .handlers import handle_command

admin_menu = on_command(
    '超管菜单', permission=SUPERUSER, priority=10, block=True,
    state={'avalon_feature': '管理员', 'avalon_command': '超管菜单'},
)


@admin_menu.handle()
async def handle_admin_menu(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


grant_coins = on_command(
    '给代币', permission=SUPERUSER, priority=10, block=True,
    state={'avalon_feature': '管理员', 'avalon_command': '给代币'},
)


@grant_coins.handle()
async def handle_grant_coins(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


grant_world_coins = on_command(
    '给世界币', permission=SUPERUSER, priority=10, block=True,
    state={'avalon_feature': '管理员', 'avalon_command': '给世界币'},
)


@grant_world_coins.handle()
async def handle_grant_world_coins(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


grant_stamina = on_command(
    '给体力', permission=SUPERUSER, priority=10, block=True,
    state={'avalon_feature': '管理员', 'avalon_command': '给体力'},
)


@grant_stamina.handle()
async def handle_grant_stamina(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


grant_exp = on_command(
    '给经验', permission=SUPERUSER, priority=10, block=True,
    state={'avalon_feature': '管理员', 'avalon_command': '给经验'},
)


@grant_exp.handle()
async def handle_grant_exp(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


grant_pity = on_command(
    '给保底', permission=SUPERUSER, priority=10, block=True,
    state={'avalon_feature': '管理员', 'avalon_command': '给保底'},
)


@grant_pity.handle()
async def handle_grant_pity(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


grant_tower = on_command(
    '给爬塔', aliases={'给爬塔次数'}, permission=SUPERUSER, priority=10, block=True,
    state={'avalon_feature': '管理员', 'avalon_command': '给爬塔'},
)


@grant_tower.handle()
async def handle_grant_tower(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


grant_item = on_command(
    '给物品', permission=SUPERUSER, priority=10, block=True,
    state={'avalon_feature': '管理员', 'avalon_command': '给物品'},
)


@grant_item.handle()
async def handle_grant_item(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


grant_items = on_command(
    '批量给物品', permission=SUPERUSER, priority=10, block=True,
    state={'avalon_feature': '管理员', 'avalon_command': '批量给物品'},
)


@grant_items.handle()
async def handle_grant_items(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


remove_item = on_command(
    '删除物品', aliases={'删物品'}, permission=SUPERUSER, priority=10, block=True,
    state={'avalon_feature': '管理员', 'avalon_command': '删除物品'},
)


@remove_item.handle()
async def handle_remove_item(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


remove_equipped = on_command(
    '删除装备', aliases={'删装备'}, permission=SUPERUSER, priority=10, block=True,
    state={'avalon_feature': '管理员', 'avalon_command': '删除装备'},
)


@remove_equipped.handle()
async def handle_remove_equipped(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


grant_prop = on_command(
    '给道具', permission=SUPERUSER, priority=10, block=True,
    state={'avalon_feature': '管理员', 'avalon_command': '给道具'},
)


@grant_prop.handle()
async def handle_grant_prop(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


remove_prop = on_command(
    '删除道具', aliases={'删道具'}, permission=SUPERUSER, priority=10, block=True,
    state={'avalon_feature': '管理员', 'avalon_command': '删除道具'},
)


@remove_prop.handle()
async def handle_remove_prop(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


create_redeem_code = on_command(
    '生成兑换码', permission=SUPERUSER, priority=10, block=True,
    state={'avalon_feature': '管理员', 'avalon_command': '生成兑换码'},
)


@create_redeem_code.handle()
async def handle_create_redeem_code(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


makeup_checkin = on_command(
    '补签', permission=SUPERUSER, priority=10, block=True,
    state={'avalon_feature': '管理员', 'avalon_command': '补签'},
)


@makeup_checkin.handle()
async def handle_makeup_checkin(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


force_boss = on_command(
    '必遇', permission=SUPERUSER, priority=10, block=True,
    state={'avalon_feature': '管理员', 'avalon_command': '必遇'},
)


@force_boss.handle()
async def handle_force_boss(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


festival = on_command(
    '节日福利', permission=SUPERUSER, priority=10, block=True,
    state={'avalon_feature': '管理员', 'avalon_command': '节日福利'},
)


@festival.handle()
async def handle_festival(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


list_users = on_command(
    '用户列表', permission=SUPERUSER, priority=10, block=True,
    state={'avalon_feature': '管理员', 'avalon_command': '用户列表'},
)


@list_users.handle()
async def handle_list_users(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


grant_week_card = on_command(
    '给周卡', permission=SUPERUSER, priority=10, block=True,
    state={'avalon_feature': '管理员', 'avalon_command': '给周卡'},
)


@grant_week_card.handle()
async def handle_grant_week_card(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


grant_month_card = on_command(
    '给月卡', permission=SUPERUSER, priority=10, block=True,
    state={'avalon_feature': '管理员', 'avalon_command': '给月卡'},
)


@grant_month_card.handle()
async def handle_grant_month_card(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


grant_year_card = on_command(
    '给年卡', permission=SUPERUSER, priority=10, block=True,
    state={'avalon_feature': '管理员', 'avalon_command': '给年卡'},
)


@grant_year_card.handle()
async def handle_grant_year_card(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


custom_gem = on_command(
    '定制宝石', permission=SUPERUSER, priority=10, block=True,
    state={'avalon_feature': '管理员', 'avalon_command': '定制宝石'},
)


@custom_gem.handle()
async def handle_custom_gem(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)


remove_custom_gem = on_command(
    '删除定制宝石', permission=SUPERUSER, priority=10, block=True,
    state={'avalon_feature': '管理员', 'avalon_command': '删除定制宝石'},
)


@remove_custom_gem.handle()
async def handle_remove_custom_gem(
    event: MessageEvent,
    matcher: Matcher,
    call: Annotated[GameCall, Depends(get_game_call)],
) -> None:
    await handle_command(event, matcher, call)
