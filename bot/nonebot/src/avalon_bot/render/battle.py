"""聊天战报：一回合一个标题，保留实际出手顺序，分页重复战斗上下文。"""

from __future__ import annotations

from collections import defaultdict

from .markdown import code_card

KINDS = {'normal': '普通', 'elite': '精英', 'boss': 'BOSS', 'hidden': '隐秘'}


def battle_summary(battle: dict) -> str:
    outcome = ('胜利' if battle.get('won') else '平局' if battle.get('draw')
               else '超过回合上限，挑战失败' if battle.get('timeout') else '战败')
    return f'{outcome}，{battle.get("rounds", 0)} 回合；生命 {_hp(battle.get("player_hp", 0), battle.get("player_max_hp"))}'


def _hp(current, maximum) -> str:
    return str(current) if maximum is None else f'{current}/{maximum}'


def _monster_title(monster: dict) -> str:
    prefix = [KINDS.get(monster['kind'], monster['kind'])] if monster.get('kind') else []
    if 'level' in monster:
        prefix.append(f'Lv.{monster["level"]}')
    return ' '.join([*prefix, monster.get('name', '怪物')])


def _fights(data: dict):
    if 'fights' in data:
        for fight in data['fights']:
            d, m, b = fight['dungeon'], fight['monster'], fight['battle']
            tail = []
            if b.get('won'):
                tail = [f'回复生命 {fight["heal"]}']
            yield f'{d["id"]}.{d["name"]} {_monster_title(m)}', m.get('name', '怪物'), b, tail
    elif data.get('steps') is not None:
        roles = {'chain': '连战', 'double': '连战符', 'hidden': '隐秘战'}
        for step in data['steps']:
            if step.get('battle'):
                m = step.get('monster', {})
                role = roles.get(step.get('role'), '')
                yield (f'【{role}】' if role else '') + _monster_title(m), m.get('name', '怪物'), step['battle'], []
    elif data.get('battle'):
        if 'steps' in data['battle']:
            yield from _fights(data['battle'])
        else:
            yield '世界BOSS', '世界BOSS', data['battle'], []


def _turn_lines(name: str, battle: dict, turn: dict) -> list[str]:
    player = turn['side'] == 'player'
    actor, target = ('你', name) if player else (name, '你')
    remain, maximum = ('monster_hp', 'monster_max_hp') if player else ('player_hp', 'player_max_hp')
    hp = f'{target}HP {_hp(turn.get(remain, 0), battle.get(maximum))}'
    parts = turn.get('parts', [])
    damage = turn.get('damage', max(0, turn.get('total', 0) - sum(value for _, value in parts)))
    shield = f'（护盾吸收 {turn["absorbed"]}）' if turn.get('absorbed') else ''
    lines = []
    only_effect = damage == 0 and parts and not turn.get('dodged') and not turn.get('absorbed') and not turn.get('crit')
    if turn.get('dodged'):
        lines.append(f'{target} 闪避 → {hp}')
    elif not only_effect:
        kind = '暴击伤害' if turn.get('crit') else '伤害'
        lines.append(f'{actor}造成 {damage} {kind}{shield}→ {hp}')
    # total 已含主攻击及效果伤害，不能再把 total 当成主攻击展示一遍。
    lines.extend(f'{label}：{value} 伤害' for label, value in parts)
    if only_effect:
        lines[-1] += f' → {hp}'
    lines.extend(turn.get('notes', []))
    return lines


def _blocks(name: str, battle: dict, tail: list[str]) -> list[tuple[str, list[str]]]:
    """连续同回合出手放一起；不能按双方配对，否则连击/回合效果会丢失。"""
    blocks = []
    if battle.get('notes'):
        blocks.append(('', list(battle['notes'])))
    turns = battle.get('turns', [])
    before, action_notes = defaultdict(list), defaultdict(list)
    for note in battle.get('notes_timeline', []):
        index = min(len(turns), max(0, note['turn_index']))
        if note['phase'] == 'round_start':
            # 原版翎羽祝福写在当回合玩家出手的备注里，不能把所有回合的祝福提到开场。
            target = next((i for i in range(index, len(turns))
                           if turns[i]['round_no'] == note['round_no'] and turns[i]['side'] == note['side']), None)
            if target is not None:
                action_notes[target].append(note['text'])
                continue
        before[index].append(note)

    def add(number, lines):
        title = f'第{number}回合' if number else ''
        if blocks and blocks[-1][0] == title:
            blocks[-1][1].extend(lines)
        else:
            blocks.append((title, list(lines)))

    for index, turn in enumerate(turns):
        for note in before[index]:
            add(note['round_no'], [note['text']])
        shown = {**turn, 'notes': [*action_notes[index], *turn.get('notes', [])]}
        add(turn['round_no'], _turn_lines(name, battle, shown))
    for note in before[len(turns)]:
        add(note['round_no'], [note['text']])
    if not turns:
        blocks.append(('', ['无出手']))
    summary = [f'{label}{battle[key]}' for key, label in (
        ('player_crits', '暴击'), ('player_dodges', '自己闪避'), ('monster_dodges', '对方闪避')) if battle.get(key)]
    blocks[-1][1].extend([*([' '.join(summary)] if summary else []), battle_summary(battle), *tail])
    return blocks


def battle_details(data: dict) -> str:
    rows = []
    for heading, name, battle, tail in _fights(data):
        if rows:
            rows.append('')
        rows.append(heading)
        for title, lines in _blocks(name, battle, tail):
            rows.extend([*([title] if title else []), *lines])
    return code_card('爬塔详情' if 'fights' in data else '战报详情', rows or ['没有可查看的战斗记录'])


def battle_pages(data: dict, limit: int = 2400) -> list[str]:
    """优先整回合换页；超长效果备注才拆行，每页都有战斗和回合上下文。"""
    if limit < 256:
        raise ValueError('战报分页长度过小')
    title = '爬塔详情' if 'fights' in data else '战报详情'
    pages, rows = [], []

    def fits(lines):
        return len(code_card(title, lines)) <= limit

    def flush():
        if rows:
            pages.append(code_card(title, rows))
            rows.clear()

    for heading, name, battle, tail in _fights(data):
        first = True
        # 标题来自规则数据，限制极端长标题以确保每页仍可容纳正文。
        heading = heading[:limit // 3]
        for round_title, body in _blocks(name, battle, tail):
            prefix = ([''] if rows else []) + [heading] if first else []
            block = [*([round_title] if round_title else []), *body]
            if fits([*rows, *prefix, *block]):
                rows.extend([*prefix, *block])
            else:
                flush()
                context = heading if first else heading + '（续）'
                if fits([context, *block]):
                    rows.extend([context, *block])
                else:
                    # 一回合或一条效果备注本身超过一页，标注“续”且不丢字。
                    rows.extend([context, *([round_title] if round_title else [])])
                    for original in body:
                        safe = original.replace('```', '``\u200b`')
                        width = limit // 3
                        lines = [piece for line in safe.split('\n') for piece in
                                 ([line[i:i + width] for i in range(0, len(line), width)] or [''])]
                        for line in lines:
                            if not fits([*rows, line]):
                                flush()
                                rows.extend([heading + '（续）', *([round_title + '（续）'] if round_title else [])])
                            rows.append(line)
            first = False
    flush()
    return pages or [battle_details(data)]
