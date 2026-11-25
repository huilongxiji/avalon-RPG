"""游戏插件入口：声明元数据，按功能注册命令与通知响应器。"""

from nonebot import on_notice
from nonebot.adapters.onebot.v11 import Bot, NoticeEvent
from nonebot.matcher import Matcher
from nonebot.plugin import PluginMetadata

from ...config import BotConfig
from . import admin, battle, inventory, items, market, menus, role
from .handlers import battle_click, handle_battle_click

__plugin_meta__ = PluginMetadata(
    name='阿瓦隆游戏',
    description='角色、背包装备、道具、交易、战斗、帮助与管理指令',
    usage='发送 /帮助 查看全部指令；战斗后通过 /战报详情 [页码] 查看当前战报',
    type='application',
    config=BotConfig,
    supported_adapters={'~onebot.v11'},
)

# 导入功能模块即执行各自显式声明的 on_command 和 @响应器.handle()。
COMMAND_MODULES = (role, inventory, items, battle, market, menus, admin)
click = on_notice(rule=battle_click, priority=10, block=True)


@click.handle()
async def handle_report_button(bot: Bot, event: NoticeEvent, matcher: Matcher) -> None:
    await handle_battle_click(bot, event, matcher)
