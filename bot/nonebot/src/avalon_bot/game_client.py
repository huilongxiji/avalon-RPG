"""独立于 NoneBot 的指令执行器：可用真实 HTTP 链路回放全部聊天指令。"""

from __future__ import annotations

import asyncio
import secrets
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from urllib.parse import quote

from avalon_contracts.api.game import BY_KEY
from avalon_contracts.errors import GameError

from . import api_client
from .commands import BY_NAME, COMMANDS, parse_command
from .render.battle import battle_pages
from .render.game import render
from .tool.blue import BlueLink


@dataclass(frozen=True)
class ReplyButton:
    label: str
    data: str


@dataclass(frozen=True)
class Reply:
    text: str
    buttons: tuple[str, ...] = ()
    button_rows: tuple[tuple[str, ...], ...] = ()
    plain: bool = False
    image_help: bool = False
    superuser: bool = False
    prefix: str = ''
    header: bool = True
    actions: tuple[ReplyButton, ...] = ()
    report_id: str | None = None
    report_detail: bool = False


@dataclass
class Report:
    id: str
    at: float
    session: str
    kind: str
    pages: list[str]
    summary: str
    page: int | None = None


_pending: OrderedDict[tuple, tuple] = OrderedDict()
_reports: OrderedDict[str, Report] = OrderedDict()
_responses: OrderedDict[tuple, tuple] = OrderedDict()
_inflight: dict[tuple, tuple] = {}
_player_locks: dict[str, list] = {}
_LIMIT = 1000
_REPORT_TTL = 1800
REPORT_CALLBACK = 'battle-report:'


def _store(cache: OrderedDict, key, value):
    cache.pop(key, None)
    cache[key] = value
    while len(cache) > _LIMIT:
        cache.popitem(last=False)


@asynccontextmanager
async def _player_lock(openid: str):
    entry = _player_locks.setdefault(openid, [asyncio.Lock(), 0])
    entry[1] += 1
    try:
        async with entry[0]:
            yield
    finally:
        entry[1] -= 1
        if not entry[1]:
            _player_locks.pop(openid, None)


async def invalidate_report(openid: str) -> None:
    async with _player_lock(openid):
        _reports.pop(openid, None)


def _current_report(openid: str, session: str, report_id: str | None = None) -> Report | None:
    report = _reports.get(openid)
    if report and time.monotonic() - report.at > _REPORT_TTL:
        _reports.pop(openid, None)
        return None
    if report and report.session == session and (report_id is None or report.id == report_id):
        return report
    return None


def _cached_reply(reply: Reply, openid: str, session: str) -> Reply:
    if reply.report_id:
        report = _current_report(openid, session, reply.report_id)
        if report is None or reply.report_detail and report.page is None:
            return Reply('这份战报已失效，请在新的战斗结束后重新查看详情', plain=True)
    return reply


def _open_button(report: Report) -> tuple[ReplyButton, ...]:
    return (ReplyButton('查看详情', f'{REPORT_CALLBACK}{report.id}:open'),)


def _report_reply(key: str, query: dict, *, openid: str, session: str, prefix: str,
                  report_id: str | None) -> Reply:
    report = _current_report(openid, session, report_id)
    if report is None or key in ('tower_detail', 'tower_summary') and report.kind != 'tower':
        return Reply('还没有可查看的当前战报，或战报已失效。请先在本会话完成爬塔或战斗，再点击查看详情', plain=True)
    if key == 'tower_summary':
        report.page = None
        return Reply(report.summary, actions=_open_button(report), report_id=report.id)
    if 'page' in query and report.page is None:
        return Reply(f'指定页码只能在上一条指令为战报详情时使用，请先发送「{prefix}战报详情」打开第一页', plain=True)
    page = query.get('page', 1)
    if not 1 <= page <= len(report.pages):
        return Reply(f'页码不存在，这份战报共 {len(report.pages)} 页，请输入 1～{len(report.pages)}', plain=True)
    report.page = page
    command = prefix + '战报详情'
    footer = f'\n\n第 {page}/{len(report.pages)} 页\n\n> 想查看指定页数请发送 {BlueLink.fill(command + " ", label=command)} xxx'
    actions = tuple(ReplyButton(label, f'{REPORT_CALLBACK}{report.id}:{target}')
                    for label, target in (('上一页', page - 1), ('下一页', page + 1)))
    return Reply(report.pages[page - 1] + footer, actions=actions, report_id=report.id, report_detail=True)


def help_text(group: str = '', *, superuser: bool = False, prefix: str = '') -> str:
    lines = ['### ' + ('超管菜单' if group == 'admin' else '背包菜单' if group == '背包' else '帮助'), '']
    for command in COMMANDS:
        if command.admin and not superuser:
            continue
        if group == 'admin' and not command.admin:
            continue
        if group not in ('', 'admin') and command.group != group:
            continue
        usage = f'{prefix}{command.name} {command.usage}'.rstrip()
        if group:
            target = prefix + command.name + (' ' if command.usage else '')
            lines.append(f'> {BlueLink.fill(target, label=usage)}')
        else:
            lines.append(usage)
    return '\n'.join(lines)


async def run_command(raw: str, text: str, *, openid: str, superuser: bool = False,
                      request_id: str | None = None, session: str = '', mentions: list[str] | None = None,
                      prefix: str = '', report_id: str | None = None) -> Reply:
    """同一 OneBot 事件只处理一次，重发确认消息不能充当玩家的第二次确认。"""
    kwargs = dict(openid=openid, superuser=superuser, request_id=request_id, session=session, mentions=mentions,
                  prefix=prefix, report_id=report_id)
    async def serialized():
        async with _player_lock(openid):
            return await _run_command(raw, text, **kwargs)
    if not request_id:
        return await serialized()
    key = (openid, request_id)
    fingerprint = (raw, text, session, superuser, tuple(mentions or ()), report_id)
    previous = _responses.get(key)
    if previous and time.monotonic() - previous[0] < 3600:
        return _cached_reply(previous[2], openid, session) if previous[1] == fingerprint else Reply('同一个请求编号不能用于不同操作')
    active = _inflight.get(key)
    if active:
        if active[0] != fingerprint:
            return Reply('同一个请求编号不能用于不同操作')
        return await asyncio.shield(active[1])

    async def execute():
        try:
            reply = await serialized()
            _store(_responses, key, (time.monotonic(), fingerprint, reply))
            return reply
        finally:
            _inflight.pop(key, None)

    task = asyncio.create_task(execute())
    _inflight[key] = (fingerprint, task)
    task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
    return await asyncio.shield(task)


async def _run_command(raw: str, text: str, *, openid: str, superuser: bool = False,
                      request_id: str | None = None, session: str = '', mentions: list[str] | None = None,
                      prefix: str = '', report_id: str | None = None) -> Reply:
    command = BY_NAME.get(raw)
    if command is None or command.name not in ('战报详情', '爬塔详情', '爬塔概括'):
        _reports.pop(openid, None)
    elif (report := _reports.get(openid)) and report.session != session:
        _reports.pop(openid, None)
    elif command.name == '爬塔概括' and report:
        report.page = None
    if command is None:
        return Reply('没有这个指令', plain=True)
    if command.admin and not superuser:
        return Reply('没有权限', plain=True)
    try:
        parsed = parse_command(raw, text, mentions)
        if parsed.key in ('help', 'bag_help', 'admin_help'):
            if parsed.key == 'help' and text.strip() in ('?', '？'):
                rows = (('签到', '面板'), ('背包菜单', '市场', '副本')) + ((('超管菜单',),) if superuser else ())
                return Reply('### 快捷指令', button_rows=rows, header=False)
            return Reply(help_text({'help': '', 'bag_help': '背包', 'admin_help': 'admin'}[parsed.key], superuser=superuser, prefix=prefix),
                         image_help=parsed.key == 'help', superuser=superuser, prefix=prefix, header=False)
        if parsed.key == 'redeem_help':
            return Reply(f'用法: {prefix}兑换 <兑换码>', plain=True)
        if parsed.key in ('tower_detail', 'tower_summary', 'battle_detail'):
            return _report_reply(parsed.key, parsed.query, openid=openid, session=session, prefix=prefix, report_id=report_id)
        operation = BY_KEY[parsed.key]
        parameters = {'openid': openid, **parsed.path}
        path = operation.path
        for name, value in parameters.items():
            path = path.replace('{' + name + '}', quote(str(value), safe=''))
        pending_key = (openid, session, command.name, text.strip())
        pending = _pending.get(pending_key)
        if (pending and time.monotonic() - pending[0] < 60 and parsed.key in ('enhance', 'tower')
                and (not request_id or request_id != pending[2])):
            _pending.pop(pending_key, None)
            parsed.body['confirmed'] = True
            if parsed.key == 'enhance':
                parsed.body['expected_level'] = pending[1].get('level')
                parsed.body['expected_name'] = pending[1].get('name')
        query = {**parsed.query, **({'with_rules': 'true'} if parsed.key in ('market', 'rank') else {})}
        kwargs = {'openid': openid, 'superuser': superuser, 'request_id': request_id, 'params': query}
        if operation.body:
            kwargs['json'] = parsed.body
        try:
            data = await api_client.call(operation.method, '/api/v1' + path, **kwargs)
        except GameError as exc:
            if exc.code == 'confirm':
                _store(_pending, pending_key, (time.monotonic(), exc.detail, request_id))
                if parsed.key == 'enhance':
                    return Reply(f'### 强化确认\n\n- 装备：**{exc.detail.get("name", "")} +{exc.detail.get("level", 0)}**\n'
                                 f'- 成功率：**{exc.detail.get("chance", 0) * 100:g}%**\n- 消耗：**{exc.detail.get("cost", 0)}** 代币\n'
                                 f'- 60 秒内再次发送「{prefix}{raw} {text}」确认。')
                return Reply(f'### 爬塔确认\n\n- 今日免费爬塔次数已用完，已挑战 **{exc.detail.get("used", 0)}** 次\n'
                             f'- 本次需要消耗 **{exc.detail.get("cost", 0)}** 体力，当前 **{exc.detail.get("stamina", 0)}**\n'
                             f'- 60 秒内再次发送「{prefix}爬塔」确认。', ('爬塔',))
            raise
        battle = parsed.key in ('dungeon', 'tower', 'boss') or (parsed.key == 'prop_use' and data.get('battle'))
        if parsed.key == 'tower' and not data.get('fights'):
            battle = False
        buttons = ('面板', '背包') if parsed.key in ('checkin', 'equip', 'unequip') else ()
        text = render(parsed.key, data, title=command.name, query=parsed.query, prefix=prefix, request=parsed.body,
                      private=not session.startswith('group_'))
        if battle:
            report = Report(secrets.token_urlsafe(12), time.monotonic(), session, parsed.key, battle_pages(data), text)
            _store(_reports, openid, report)
            return Reply(text, actions=_open_button(report), report_id=report.id)
        rows = (('上架 ', '下架 '), ('购买 ',)) if parsed.key == 'market' else ()
        plain = parsed.key in ('prop_craft', 'shop_buy') or not text.startswith('###') and parsed.key != 'prop_use'
        return Reply(text, buttons, button_rows=rows, plain=plain, header=parsed.key != 'shop')
    except GameError as exc:
        message = exc.message
        if message.startswith('用法: '):
            message = message.replace('用法: ', '用法: ' + prefix, 1)
        if exc.code == 'cooldown':
            message += f'（剩余 {exc.detail.get("cooldown_left", 0)} 秒）'
        if exc.code in ('fragment', 'material') and exc.detail.get('blurb'):
            return Reply(message + '\n> ' + exc.detail['blurb'])
        return Reply(message, plain=True)
