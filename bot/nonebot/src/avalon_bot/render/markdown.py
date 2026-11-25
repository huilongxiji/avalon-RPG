"""QQ 卡片通用排版与分页；代码框不能在消息边界处断开。"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse


def code_card(title: str, rows: list[str], *, before: str = '') -> str:
    # 玩家名称等不能提前关闭代码框。
    body = '\n'.join(rows).replace('```', '``\u200b`')
    return f'### {title}\n\n' + (before + '\n\n' if before else '') + f'```json\n{body}\n```'


def plain_text(markdown: str) -> str:
    def link(match):
        label, url = match.groups()
        if url.startswith('mqqapi:'):
            command = parse_qs(urlparse(url).query).get('command', [''])[0].strip()
            return label if label == command else f'{label}（{command}）'
        return f'{label}（{url}）'

    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', markdown)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', link, text)
    text = re.sub(r'^```[^\n]*\n?', '', text, flags=re.M)
    text = re.sub(r'^(?:#{1,6}|>)\s*', '', text, flags=re.M)
    text = re.sub(r'^\|[\s:|\-]+\|\s*$', '', text, flags=re.M)
    text = '\n'.join(' / '.join(c.strip() for c in line.strip('|').split('|'))
                     if line.startswith('|') else line for line in text.splitlines())
    return text.replace('**', '').replace('`', '').replace('\\|', '|')


def paginate(markdown: str, limit: int = 2800) -> list[str]:
    """按行分页，每页独立闭合并重开代码框；给头像、页码和按钮预留空间。"""
    if limit < 64:
        raise ValueError('分页长度过小')
    pages, lines, size = [], [], 0
    fence = ''
    # 极长一行（例如堆叠战斗备注）也必须有上限。
    for original in markdown.splitlines():
        parts = [original[i:i + limit - 24] for i in range(0, len(original), limit - 24)] or ['']
        for line in parts:
            closing = bool(fence and line == '```')
            reserve = 0 if closing else 4
            if lines and size + len(line) + 1 + reserve > limit:
                pages.append('\n'.join([*lines, *(['```'] if fence else [])]))
                lines = [fence] if fence else []
                size = len(fence) + 1 if fence else 0
            lines.append(line)
            size += len(line) + 1
            if line.startswith('```'):
                fence = '' if fence else line
    if lines:
        pages.append('\n'.join([*lines, *(['```'] if fence else [])]))
    return pages or ['']
