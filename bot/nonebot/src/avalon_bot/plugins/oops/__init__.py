"""未预期异常记录在 bot 日志，玩家得到稳定的中文提示。"""

from __future__ import annotations

import logging

from nonebot.adapters.onebot.v11 import Bot, Event
from nonebot.message import run_postprocessor
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name='游戏异常处理', description='记录命令和按钮通知的未预期异常，返回中文提示', usage='自动生效，无指令',
    type='application', supported_adapters={'~onebot.v11'},
)

log = logging.getLogger('avalon_bot.oops')


@run_postprocessor
async def report(bot: Bot, event: Event, exception: Exception | None) -> None:
    if exception is None:
        return
    log.error('处理游戏指令失败', exc_info=(type(exception), exception, exception.__traceback__))
    try:
        await bot.send(event, '处理失败，错误已记录，请稍后再试')
    except Exception:
        log.warning('发送错误提示失败', exc_info=True)
