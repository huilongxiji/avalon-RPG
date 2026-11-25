"""结构化结果的中文排版；所有价格、属性、掉落和奖励直接使用 API 返回值。"""

from __future__ import annotations

from datetime import datetime

from ..tool.at_user import AtUser
from ..tool.blue import BlueLink
from .battle import battle_details, battle_summary  # noqa: F401 -- 保持公开导入路径
from .markdown import code_card, plain_text  # noqa: F401 -- 保持公开导入路径

STAT_NAMES = {'hp': '生命', 'atk': '攻击', 'defense': '防御', 'agi': '敏捷', 'mp': '法力', 'crit': '暴击率',
              'dodge': '闪避率', 'crit_dmg': '爆伤', 'penetration': '固定穿透', 'pen_pct': '百分比穿透',
              'dmg_reduce': '免伤', 'hp_pct': '生命加成', 'atk_pct': '攻击加成', 'defense_pct': '防御加成'}
SLOT_LABELS = {'weapon': '武器', 'armor': '护甲', 'bracelet': '手镯', 'necklace': '项链', 'gem': '宝石'}
LABELS = {'name': '名称', 'quantity': '数量', 'current': '现有', 'removed': '删除', 'remaining': '剩余',
          'coins': '代币余额', 'world_coins': '世界币余额', 'cost': '花费', 'payout': '获得代币', 'refund': '返还代币',
          'old_level': '原强化等级', 'new_level': '当前强化等级', 'failed_at': '失败等级', 'enhance': '强化等级',
          'temper': '淬炼度', 'added': '提升', 'kinds': '背包容量', 'output': '产物', 'essence': '精华',
          'pity': '保底', 'pity_total': '当前保底', 'listing_id': '挂单编号', 'unit_price': '单价', 'paid': '花费',
          'fee': '手续费', 'seller_gain': '卖家所得', 'days': '补签天数', 'gained': '获得体力', 'count': '累计签到',
          'streak': '连续签到', 'owed': '未补天数', 'stamina': '当前体力', 'exp': '经验', 'level': '等级', 'price': '基础单价',
          'current_exp': '当前经验', 'exp_to_next': '升级所需经验', 'levels_gained': '提升等级', 'levels_lost': '降低等级',
          'bonus': '额外爬塔次数', 'detail': '结果', 'blurb': '说明', 'restored': '恢复连续签到', 'replaced': '换下装备'}


def item_name(name: str, level: int = 0) -> str:
    return f'{name} +{level}' if level else name


def stat_lines(data: dict, *, owned: bool = False) -> list[str]:
    meta = data.get('stat_meta') or [{'key': k, 'name': v, 'percent': k in
             ('crit', 'crit_dmg', 'dodge', 'pen_pct', 'dmg_reduce', 'hp_pct', 'atk_pct', 'defense_pct')} for k, v in STAT_NAMES.items()]
    return [f'{s["name"]}：{data["stats"].get(s["key"], 0):g}{"%" if s["percent"] else ""}'
            for s in meta if not owned or s['key'] in data['stats']]


def facts(data: dict) -> list[str]:
    if data.get('text'):
        return ['- ' + data['text']]
    lines = []
    for key, label in LABELS.items():
        value = data.get(key)
        if value is not None and value != '' and not isinstance(value, (dict, list)):
            lines.append(f'- {label}：**{value}**')
    return lines


def _battles(data: dict):
    for step in data.get('steps', []):
        if step.get('battle'):
            yield step.get('monster', {}).get('name', '怪物'), step['battle']
    for fight in data.get('fights', []):
        yield fight.get('monster', {}).get('name', '怪物'), fight['battle']
    if data.get('battle'):
        if 'steps' in data['battle']:
            yield from _battles(data['battle'])
        elif 'turns' in data['battle']:
            yield '世界BOSS', data['battle']


def _grant(data: dict | None) -> list[str]:
    if not data:
        return []
    lines = [f'- 获得经验 **{data.get("exp", 0)}**，代币 **{data.get("coins", 0)}**']
    for item in data.get('items', []):
        if item.get('error') == 'sold':
            lines.append(f'- **{item["name"]}** ×**{item["quantity"]}**，背包放不下，自动出售获得 **{item.get("payout", 0)}** 代币')
        elif item.get('ok'):
            lines.append(f'- **{item["name"]}** ×**{item["quantity"]}**')
    if data.get('levels_gained'):
        lines.append(f'- 提升等级 **{data["levels_gained"]}**，当前等级 **{data.get("level", 0)}**')
    if 'current_exp' in data:
        lines.append(f'- 经验 **{data["current_exp"]}/{data["exp_to_next"]}** · 代币 **{data["coin_balance"]}**')
    return lines


def _step_notes(step: dict) -> list[str]:
    kind = step.get('kind')
    simple = {'pity_forced': '触发保底：必遇 BOSS', 'pinned': '必遇已生效', 'gem_boss': '定制宝石：必遇 BOSS',
              'hidden_miss': '没有发现隐秘怪物'}
    if kind in simple:
        return ['- ' + simple[kind]]
    if kind == 'hidden_appear':
        return [f'- 隐秘怪物 **{step["monster"]["name"]}** 出现']
    if kind == 'hidden_gem':
        return [f'- 获得隐秘宝石，扣除保底 **{step["cut"]}**']
    if kind == 'bless':
        return [f'- 祝福：经验加成 **{step["exp_pct"]}%**' + ('，等级差效果已生效' if step.get('active') else '')]
    if kind == 'explore':
        return ['- 探寻：' + '、'.join(step['bits'])]
    if kind == 'gem_gain':
        return [f'- 宝石奖励：保底 **+{step["pity"]}**，体力 **+{step["stamina"]}**']
    if kind == 'boss_progress':
        return [f'- 必遇进度 **{step["fights"]}/{step["every"]}**']
    if kind == 'charm':
        return [f'- 道具效果生效，遭遇 **{step["monster"]}**']
    return []


def _equipment(data: dict, *, table: bool = True) -> list[str]:
    item = data['item']
    rows = [f'- {SLOT_LABELS.get(item["slot"], "物品")}：**{item_name(item["name"], data["enhance"])}**',
            f'- 基础价格：**{item["price"]}**',
            f'- 淬炼度：**+{data["temper"]}%**（上限 +{data.get("temper_cap", 10)}%，与强化乘算）',
            f'- 强化：**+{data["enhance"]}**', f'- 下一级花费：**{data.get("next_cost", 0)}**',
            f'- 累计强化：**{data.get("total_cost", 0)}**', f'- 出售返还强化：**{data.get("refund", 0)}**', '']
    if table:
        rows.extend(['| 属性 | 基础 | 当前 | 强化 |', '| :--- | :---: | :---: | :---: |'])
    for key in ('hp', 'atk', 'defense', 'agi', 'mp'):
        base = data.get('base_stats', item.get('stats', {})).get(key, 0)
        current = data['stats'].get(key, 0)
        upgraded = data.get('next_stats', {}).get(key, 0)
        rows.append(f'| {STAT_NAMES[key]} | {base:g} | {current:g} | {upgraded:g} |' if table
                    else f'- {STAT_NAMES[key]}：**{base:g}** -> **{current:g}**')
    special = {**data, 'stats': {k: v for k, v in data['stats'].items()
                               if k not in ('hp', 'atk', 'defense', 'agi', 'mp') and v}}
    if special['stats']:
        rows.extend(['', '- 特殊属性：' + '，'.join(stat_lines(special, owned=True))])
    if data.get('sponsor_features'):
        rows.extend(['', '- 定制功能：', *['- ' + s for s in data['sponsor_features']]])
    for entry in data.get('detail', {}).get('sets', []):
        rows.extend(['', '- 套装:' + entry['name']])
        for tier in entry.get('tiers', []):
            rows.extend(f'- [{tier["pieces"]}件套] {e.get("desc") or e["name"]}' for e in tier.get('effects', []))
    rows.extend('- ' + (e.get('desc') or e['name']) for e in data.get('detail', {}).get('own_effects', []))
    return rows


def _boss_rewards(rules: dict) -> str:
    if not rules:
        return ''
    tiers = '，'.join(f'{"第1名" if cap == 1 else f"前{cap}名"} {coins}世界币' for cap, coins in rules['reward_tiers'])
    return f'- 每日 **{rules["settle_hour"]}:00** 结算：{tiers}，其余参与者 {rules["participation_coins"]}'


def render(key: str, data, *, title: str = '', query: dict | None = None,
           prefix: str = '', request: dict | None = None, private: bool = True) -> str:
    title = {'equip': '装备成功', 'unequip': '卸下成功', 'temper': '淬炼成功', 'sell': '出售成功',
             'sell_many': '批量出售成功', 'decompose': '分解成功', 'expand': '背包扩容成功', 'craft': '合成成功',
             'listing': '上架成功', 'buy': '购买成功', 'cancel': '下架成功', 'makeup': '补签成功'}.get(key, title)
    if key == 'enhance':
        title = '强化失败' if data.get('failed_at') is not None else '强化成功'
    lines = [f'### {title or "操作成功"}', '']
    if key == 'checkin':
        if data['already_today']:
            return '你已经签到过了'
        bonus = data.get('bonus') or {}
        stamina = bonus.get('stamina_total') if bonus.get('stamina_total') is not None else data['stamina']
        pity = bonus.get('pity_total') if bonus.get('pity_total') is not None else data['pity']
        lines = ['### 签到成功', '']
        if data['created']:
            lines.extend(['已创建角色', ''])
        lines.extend([f'- 今日第 **{data["rank"]}** 个签到', f'- 个人签到次数 **{data["count"]}**',
                      f'- 连续签到 **{data["streak"]}** 天', f'- 获得体力 **{data["gained"]}**', f'- 当前体力 **{stamina}**'])
        if data.get('pity_gained'):
            lines.append(f'- 获得保底 **{data["pity_gained"]}**，当前 **{pity}**')
        elif bonus.get('pity_total') is not None:
            lines.append(f'- 当前保底 **{pity}**')
        lines.extend(f'- {line}' for line in bonus.get('lines', []))
        if data.get('owed', 0) > 0:
            lines.append(f'- 还缺 **{data["owed"]}** 天未补，补完后恢复连续天数')
    elif key == 'panel':
        lines = [f'等级：{data["level"]}（{data["exp"]}/{data["exp_to_next"]}）']
        for k in ('hp', 'atk', 'defense', 'agi', 'mp'):
            base = data.get('base_stats', data['stats']).get(k, 0)
            bonus = data.get('stat_bonus', {}).get(k, 0)
            lines.append(f'{STAT_NAMES[k]}：{base:g}' + (f'（{bonus:+g}）' if bonus else ''))
        lines.extend([f'暴击：{data["stats"].get("crit", 0):g}%/{data["stats"].get("crit_dmg", 0):g}%',
                      f'闪避率：{data["stats"].get("dodge", 0):g}%', f'免伤：{data["stats"].get("dmg_reduce", 0):g}%'])
        # 新增的规则属性仍展示；旧版固定显示的核心属性顺序不变。
        extra = {k: v for k, v in data['stats'].items() if v and k not in
                 ('hp', 'atk', 'defense', 'agi', 'mp', 'crit', 'crit_dmg', 'dodge', 'dmg_reduce')}
        lines.extend(stat_lines({**data, 'stats': extra}, owned=True))
        lines.extend([f'伤害类型：{data["damage_label"]}', f'代币：{data["coins"]}', f'世界币：{data["world_coins"]}',
                      f'体力：{data["stamina"]}/{data["special_stamina"]}', f'保底值：{data["pity"]}'])
        lines.extend(f'{label}：{item_name(data[slot], data[slot + "_enhance"])}' for slot, label in SLOT_LABELS.items())
        if data.get('set_details'):
            lines.extend(['--------------------', '套装'])
            for entry in data['set_details']:
                lines.append(f'{entry["name"]} {entry["count"]}/{entry["total"]}')
                for tier in entry['tiers']:
                    lines.extend(f'[{tier["pieces"]}件套] {desc}（{"已生效" if tier["active"] else "未激活"}）'
                                 for desc in tier['descriptions'])
        return code_card('玩家属性', lines)
    elif key == 'profile':
        registered = datetime.fromtimestamp(data['created_at']).strftime('%Y-%m-%d %H:%M')
        return code_card('个人信息', [f'openid：{data["openid"]}', f'user_id：{data["user_id"]}', f'name：{data["name"]}', f'注册时间：{registered}'])
    elif key in ('bag', 'sort'):
        lines, last = [], ''
        for row in data['items']:
            label = SLOT_LABELS.get(row.get('slot'), '其他')
            if label != last:
                lines.append(label)
                last = label
            lines.append(f'{row["index"]}：{item_name(row["name"], row["enhance"])} x{row["quantity"]}')
        if not data['items']:
            lines.append('背包是空的')
        hint = (str(BlueLink.fill(prefix + '装备详情 ', label='点击此处')) + '填写序号查询指定装备详情'
                if key == 'bag' else '已按部位分类，部位内按装备编号排序')
        return code_card(f'{"背包" if key == "bag" else "整理背包"}（{len(data["items"])}/{data["capacity"]}）', lines, before='> ' + hint)
    elif key == 'warehouse':
        return code_card('仓库', [f'{r["slot"]} {r["name"]} x{r["quantity"]}' for r in data]) if data else '仓库是空的'
    elif key in ('equipped', 'bag_detail'):
        title = '装备详情' if key == 'bag_detail' else '查看' + SLOT_LABELS.get(data['item']['slot'], '装备')
        lines = [f'### {title}', '', *_equipment(data)]
    elif key in ('recipes', 'prop_recipes'):
        if key == 'prop_recipes':
            return code_card('道具合成', [r['name'] + '：' + '+'.join(f'{v["name"]}*{v["quantity"]}' for v in r['inputs']) for r in data]) if data else '没有道具配方'
        rows = [f'{r["id"]}. ' + ' + '.join(f'{v["name"]} x{v["quantity"]}' for v in r['inputs'])
                + f' -> {r["output"]} x{r["quantity"]}' for r in data]
        return code_card('合成配方', ['合成配方', *rows] if rows else ['暂无合成配方'])
    elif key == 'market':
        rows, rules = (data, {}) if isinstance(data, list) else (data['items'], data['rules'])
        hint = str(BlueLink.fill(prefix + '详情 ', label='点击这里')) + '填写序号来查看指定商品的详情'
        fee = f'- 上架收 **{rules["fee_percent"]}%** 手续费 · 每周最多上架 **{rules["list_limit"]}** 次\n\n' if rules else ''
        return code_card('市场', [f'{r["id"]}：{item_name(r["name"], r["enhance"])} x{r["quantity"]} 单价 {r["unit_price"]}' for r in rows]
                         or ['市场是空的'], before=fee + '> ' + hint)
    elif key == 'market_detail':
        lines = ['### 商品详情', '', f'- 编号 **{data["id"]}**', f'- **{item_name(data["name"], data["enhance"])}** x**{data["quantity"]}**',
                 f'- 单价 **{data["unit_price"]}**']
        if data.get('equipment') and data['equipment']['item']['slot'] in SLOT_LABELS:
            lines.extend(_equipment(data['equipment'], table=False))
    elif key == 'shop':
        world = (query or {}).get('kind') == 'world'
        kind = '世界币' if world else '土罐'
        lines = [f'### 商城 {kind}', '']
        if world:
            lines.extend([f'- 世界币余额 **{data.get("world_coins", 0)}**', ''])
        for row in data['world' if world else 'boxes']:
            lines.append(f'{row["id"]}. {row["name"]} {row["price"]}世界币' if world else
                         f'- {row["id"]} {row.get("dungeon", "")}：{row["name"]} **{row["price"]}** 代币（需 {row["level"]} 级）')
        lines.extend(['', f'> 用法: {prefix}商城 {kind} <编号> [数量]'])
    elif key == 'shop_buy':
        world = data.get('world_coins') is not None
        currency = '世界币' if world else '代币'
        return (f'购买成功，获得{data["name"]}×{(request or {}).get("quantity", 1)}，仓库现有{data["quantity"]}个，'
                f'花费{data["cost"]}{currency}，{currency}余额：{data["world_coins" if world else "coins"]}')
    elif key == 'prop_craft':
        qty = (request or {}).get('quantity', 1)
        return f'合成成功，获得{data["name"]}' + (f'x{qty}' if qty > 1 else '') + f'，仓库现有{data["quantity"]}个'
    elif key == 'redeem':
        return code_card('兑换成功', [f'{data["name"]} x{data["detail"]}', f'仓库现有 {data["quantity"]}'])
    elif key in ('dungeons', 'dungeon_guide'):
        rows = []
        for d in data if isinstance(data, list) else [data]:
            rows.append(f'{d["id"]}.{d["name"]}  消耗 {d["stamina"]} 体力')
            for m in d['monsters']:
                kind = {'normal': '普通', 'elite': '精英', 'boss': 'BOSS', 'hidden': '隐藏'}.get(m['kind'], m['kind'])
                rows.append(f'  {m["name"]} {kind} Lv{m["level"]} 权重{m["weight"]} 代币{m["coins"]} 经验{m["exp"]}')
                if key == 'dungeon_guide':
                    rows.append('    奖池: ' + '、'.join(f'{name} {chance:g}%' for name, chance in m['pool']))
        return code_card('副本图鉴' if key == 'dungeon_guide' else '副本列表', rows or ['暂无副本'])
    elif key == 'rank':
        rows, rules = (data, {}) if isinstance(data, list) else (data['items'], data['rules'])
        lines = ['### 世界排行榜', '']
        lines.extend(f'- 第**{n}**名 {r["name"] if private else AtUser.of(r["openid"])} 伤害 **{r["damage"]}**' for n, r in enumerate(rows, 1))
        if not rows:
            lines.append('- 今日还没有人挑战')
        lines.extend(['', _boss_rewards(rules)])
    elif key == 'tower':
        # 原版首屏只含本次结果与实际奖励，逐层战斗属于二级详情。
        lines = ['### 爬塔', '']
        if data['paid']:
            cost = f'消耗体力 **{data["cost"]}**' if 'cost' in data else '付费挑战'
            lines.append(f'- {cost} · 剩余 **{data["stamina"]}**')
        else:
            lines.append(f'- 今日第 **{data["used"] + 1}** 次')
        outcome = {'cleared': '**通关**', 'lost': '**挑战结束**', 'empty': '没有可挑战的怪物'}.get(data['outcome'], data['outcome'])
        if data.get('lost_at'):
            outcome += f'，止步 **{data["lost_at"]["id"]}.{data["lost_at"]["name"]}**'
        lines.append('- ' + outcome)
        lines.extend(_grant(data.get('grant')))
        if data.get('fights'):
            lines.extend(['', f'> 发送「{prefix}战报详情」查看逐层战报'])
    elif key in ('dungeon', 'boss') or (key == 'prop_use' and data.get('battle')):
        result = data['battle'] if key == 'prop_use' else data
        if key == 'prop_use':
            lines = ['### 跨界挑战', '']
        if not result.get('steps'):
            for name, battle in _battles(data):
                lines.append(f'- **{name}**：{battle_summary(battle)}')
        for step in result.get('steps', []):
            lines.extend(_step_notes(step))
            if step.get('battle'):
                lines.append(f'- **{step["monster"]["name"]}**：{battle_summary(step["battle"])}')
            if step.get('grant'):
                lines.extend(_grant(step['grant']))
                if step.get('exp_pct') or step.get('coin_pct'):
                    lines.append(f'- 奖励加成：经验 **+{step.get("exp_pct", 0)}%**，代币 **+{step.get("coin_pct", 0)}%**')
        lines.extend(_grant(result.get('grant')))
        if key in ('dungeon', 'prop_use'):
            lines.append(f'- 保底：**{result.get("pity", 0)}**；剩余体力：**{result.get("remaining", 0)}**')
        if key == 'boss':
            record = data['record']
            lines.extend([f'- 造成伤害 **{data["damage"]}**',
                          f'- 获得普通体力 **+{record["stamina_gained"]}**（当前 **{record["stamina"]}**）'])
            if data.get('superuser'):
                lines.append('- 超管挑战：不计次数、无冷却、不计入排行榜')
            elif data.get('after_settle'):
                lines.append('- 已过结算时间，本次伤害不计入排行榜')
            else:
                lines.append(f'- 今日累计伤害 **{record["total_damage"]}**')
            if not data.get('superuser') and 'remaining_attempts' in data:
                lines.extend([f'- 今日剩余挑战次数 **{data["remaining_attempts"]}**', f'- 下次挑战冷却 **{data["cooldown"]}** 秒'])
            lines.extend(['', _boss_rewards(data.get('rules', {}))])
        lines.extend(['', f'> 发送「{prefix}战报详情」查看逐回合过程'])
    elif key == 'prop_use':
        qty = data.get('quantity', 1)
        detail = data.get('detail', '')
        text = f'使用了{data["name"]}' + (f'x{qty}' if qty > 1 else '')
        if detail.startswith('开出'):
            text += '，' + detail
        return text + '\n> ' + (data.get('blurb') or detail)
    elif key == 'admin_users':
        return code_card('用户列表', [f'{n} {r["openid"]} 等级{r["level"]} 代币{r["coins"]} 体力{r["stamina"]} 特殊{r["special_stamina"]}'
                                  for n, r in enumerate(data, 1)]) if data else '没有已注册角色'
    elif key == 'admin_action' and data.get('results') is not None:
        for row in data['results']:
            if row['ok']:
                details = row['data'] if isinstance(row['data'], list) else [row['data']]
                lines.append(f'- 目标 **{row["openid"]}**：成功')
                for detail in details:
                    lines.extend(facts(detail))
            else:
                lines.append(f'- 目标 **{row["openid"]}**：{row["error"]["message"]}')
    else:
        lines.extend(facts(data) if isinstance(data, dict) else [])
        if key == 'temper' and data.get('plan'):
            plan = data['plan']
            lines.append(f'- 基准强化 **+{plan["baseline"]}**：消耗 **{plan["gem"]}** x1，上限 **+{data["temper_cap"]}%**')
        if key == 'craft' and data.get('inputs'):
            lines.append('- 消耗：**' + ' + '.join(f'{r["name"]} x{r["quantity"]}' for r in data['inputs']) + '**')
        if isinstance(data, dict) and 'enabled' in data:
            lines.append('- **已开启**' if data['enabled'] else '- **已关闭**')
        for item in data.get('items', []) if isinstance(data, dict) else []:
            lines.extend(facts(item))
    return '\n'.join(lines)
