"""迁移后的全部游戏指令：身份与参数解析 → HTTP → 排版。"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import quote

from avalon_contracts.errors import GameError
from nonebot import get_driver
from nonebot.adapters import Event
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, MessageSegment, NoticeEvent
from nonebot.matcher import Matcher

from ... import api_client
from ...dependencies import GameCall
from ...game_client import REPORT_CALLBACK, Reply, run_command
from ...render.game import plain_text
from ...render.markdown import paginate
from ...tool.at_user import AtUser
from ...tool.button import build_buttons_json
from ...tool.interaction import Interaction
from ...tool.official import command_prefix, command_text, get_send_mode
from ...tool.segment import MessageSegmentPlus

log = logging.getLogger('avalon_bot.game')


def raw_name(raw: str) -> str:
    for prefix in sorted(get_driver().config.command_start, key=len, reverse=True):
        if prefix and raw.startswith(prefix):
            return raw[len(prefix):]
    return raw


def report_session(event: Event) -> str:
    group = Interaction.field(event, 'group_id')
    return f'group_{group}' if group else 'private'


async def send_reply(matcher: Matcher, event: Event, reply: Reply, openid: str) -> None:
    text_mode = get_send_mode() == 'text'
    if reply.image_help and not text_mode:
        from ...render.help import render_help
        from ...tool.image import FontNotFoundError

        try:
            buffer = await asyncio.to_thread(render_help, superuser=reply.superuser, prefix=reply.prefix)
        except (FontNotFoundError, OSError, ValueError):
            log.warning('帮助制图失败，回退文字', exc_info=True)
            text_mode = True
        else:
            message = MessageSegment.image(buffer)
            if getattr(event, 'message_id', None):
                message = MessageSegment.reply(event.message_id) + message
            await matcher.finish(message)
            return
    if text_mode or reply.plain:
        content = reply.text if reply.plain else plain_text(reply.text)
        if text_mode and reply.button_rows and reply.text == '### 快捷指令':
            content += '\n' + '\n'.join(command_text(name) for row in reply.button_rows for name in row)
        pages = paginate(content)
        for page in pages[:-1]:
            await matcher.send(page)
        await matcher.finish(pages[-1])
        return
    private = getattr(event, 'message_type', '') == 'private' or not getattr(event, 'group_id', None)
    rows = []
    for names in reply.button_rows or ((reply.buttons,) if reply.buttons else ()):
        buttons = [await build_buttons_json(command_text(name, blank=name.endswith(' ')), name.strip(), action_type=2,
                                           permission_type=2 if private else 0, specify_user_ids=[openid]) for name in names]
        rows.append({'buttons': buttons})
    if reply.actions:
        rows.append({'buttons': [await build_buttons_json(button.data, button.label, action_type=1,
                                                         permission_type=2 if private else 0, specify_user_ids=[openid])
                                 for button in reply.actions]})
    keyboard = {'content': {'rows': rows}} if rows else None
    header = '' if private or not reply.header else (
        f'![用户头像 #20px #20px](https://q.qlogo.cn/qqapp/1905673274/{quote(openid, safe="")}/640) | {AtUser.of(openid)}\n')
    pages = paginate(reply.text)
    for index, page in enumerate(pages):
        footer = f'\n\n第 {index + 1}/{len(pages)} 页' if len(pages) > 1 else ''
        message = MessageSegmentPlus.markdown(header + page + footer, private=private,
                                              keyboard=keyboard if index == len(pages) - 1 else None)
        if index < len(pages) - 1:
            await matcher.send(message)
        else:
            await matcher.finish(message)


async def handle_command(event: MessageEvent, matcher: Matcher, call: GameCall) -> None:
    caller = call.caller
    try:
        sender = event.sender
        await api_client.post('/api/v1/players/' + quote(caller.openid, safe='') + '/profile', openid=caller.openid,
                              request_id=caller.request_id + ':profile',
                              json={'user_id': event.get_user_id(), 'name': str(sender.card or sender.nickname or '')[:128],
                                    'group_id': getattr(event, 'group_id', None)})
        reply = await run_command(call.command, call.arguments, openid=caller.openid, superuser=caller.superuser,
                                  request_id=caller.request_id, session=caller.session, mentions=call.mentions,
                                  prefix=caller.prefix)
    except GameError as exc:
        reply = Reply(exc.message, plain=True)
    await send_reply(matcher, event, reply, caller.openid)


def battle_click(event: NoticeEvent) -> bool:
    return (getattr(event, 'notice_type', '') == 'interaction'
            and ((Interaction.button_data(event) or '').startswith(REPORT_CALLBACK)
                 or raw_name(Interaction.button_data(event) or '') in ('战报详情', '爬塔概括', '爬塔详情')))


async def handle_battle_click(bot: Bot, event: NoticeEvent, matcher: Matcher) -> None:
    openid = Interaction.field(event, 'user_openid') or Interaction.field(event, 'group_member_openid')
    if not openid:
        return
    interaction = Interaction.interaction_id(event)
    if interaction:
        try:
            await bot.call_api('put_interaction', interaction_id=interaction, code=0)
        except Exception:
            log.warning('战报按钮回执失败', exc_info=True)
    data = Interaction.button_data(event) or ''
    parts = data.removeprefix(REPORT_CALLBACK).split(':')
    if not data.startswith(REPORT_CALLBACK) or len(parts) != 2 or not parts[0] or not parts[1]:
        reply = Reply('旧战报按钮已失效，请在新的战斗结束后重新查看详情', plain=True)
    else:
        report_id, target = parts
        reply = await run_command('战报详情', '' if target == 'open' else target, openid=str(openid),
                                  request_id='interaction:' + interaction if interaction else None,
                                  session=report_session(event), prefix=command_prefix(), report_id=report_id)
    await send_reply(matcher, event, reply, str(openid))
