"""装备详情页"伤害计算"：按战斗内核的实际计算顺序，生成 Mermaid 流程图。

流程图里的方框是规则里的公式，显示公式的中文名称（网站上改了名称，图也跟着变）；
圆角框是参与计算的数值，菱形是判定。图下面逐个列出用到的公式（中文名称 + 原式）。
模板里写 F_<公式代号> 表示一个公式方框；同一个公式在一张图里出现两次时写 F_<代号>__2。
公式里调用了别的公式时，自动画出被调用的公式（虚线）。
"""

from __future__ import annotations

import re

from avalon_contracts.api.rules_admin import DamageFlow
from avalon_contracts.rules.formula import BATTLE_FORMULAS
from avalon_contracts.rules.item import ItemDef

from ..engine.ruleset import RuleSet

_LEVEL = '''
lvs(["双方等级、祝福等级"]) --> F_effective_level --> F_level_coef_taken
'''

_PLAYER_PHYSICAL = '''
atk(["攻击力"])
tdef(["目标防御"]) --> F_def_after_pen
pen(["穿透、穿透%、无视防御%"]) --> F_def_after_pen
F_def_after_pen --> F_physical_mitigation
mylv(["自己等级"]) --> F_physical_mitigation
''' + _LEVEL + '''
atk --> F_physical_damage
F_physical_mitigation --> F_physical_damage
F_level_coef_taken --> F_physical_damage
tred(["目标免伤%"]) --> F_physical_damage
F_physical_damage --> dodge{"目标闪避？"}
dodge -- 闪避 --> miss(["这次攻击伤害为 0"])
dodge -- 没闪避 --> crit{"暴击？（暴击率）"}
crit -- 暴击 --> F_crit_hit
cd(["暴击伤害"]) --> F_crit_hit
F_crit_hit --> extra
crit -- 不暴击 --> extra(["加上效果追加的物理、法术伤害"])
extra -. 有造成伤害降低时 .-> F_lessen
F_lessen -.-> mul
extra --> mul["单独增伤（幸运三角）"]
mul --> F_amplify
dpct(["增伤%"]) --> F_amplify
F_amplify --> out(["最终伤害（再加上真实伤害）"])
'''

_PRECISION = '''
agi(["自己敏捷、目标敏捷（打世界BOSS时没有）"])
agi --> F_precision_flat_pen --> pen
agi --> F_precision_pen_pct --> pen
agi --> F_precision_crit --> crit
agi --> F_precision_crit_dmg --> cd
'''

_PLAYER_MAGIC = '''
mp(["法力"])
tres(["目标法抗"]) --> F_resist_after_pen
mpen(["无视法抗、无视法抗%"]) --> F_resist_after_pen
''' + _LEVEL + '''
mp --> sub["法力 − 有效法抗"]
F_resist_after_pen --> sub
sub --> F_level_reduce
F_level_coef_taken --> F_level_reduce
tred(["目标免伤%"]) --> F_level_reduce
F_level_reduce --> F_amplify
mtk(["目标受到的法术伤害提升%（腐朽）"]) --> F_amplify
F_amplify --> dodge{"目标闪避？"}
dodge -- 闪避 --> miss(["这次攻击伤害为 0"])
dodge -- 没闪避 --> crit{"暴击？（法术暴击率）"}
crit -- 暴击 --> F_crit_hit
cd(["默认暴击伤害"]) --> F_crit_hit
F_crit_hit --> extra
crit -- 不暴击 --> extra(["加上效果追加的物理、法术伤害"])
extra -. 有造成伤害降低时 .-> F_lessen
F_lessen -.-> mul
extra --> mul["单独增伤（幸运三角）"]
mul --> F_amplify__2
dpct(["增伤%"]) --> F_amplify__2
F_amplify__2 --> out(["最终伤害（再加上真实伤害）"])
'''

_TAKEN = '''
dodge{"自己闪避？"} -- 闪避 --> miss(["不受伤害"])
dodge -- 没闪避 --> matk(["怪物攻击力"])
matk -. 世界BOSS .-> F_world_boss_atk
F_world_boss_atk -.-> F_physical_damage
mdef(["自己防御"]) --> F_def_after_pen
mpen(["怪物穿透、穿透%"]) --> F_def_after_pen
F_def_after_pen --> F_physical_mitigation
mlv(["怪物等级"]) --> F_physical_mitigation
matk --> F_physical_damage
F_physical_mitigation --> F_physical_damage
myred(["自己免伤%"]) --> F_physical_damage
lvs(["双方等级、祝福等级"]) --> F_effective_level --> F_level_coef_dealt --> F_scale_dealt
F_physical_damage --> F_scale_dealt
F_scale_dealt -. 有受到伤害降低时 .-> F_lessen
F_lessen -.-> crit
F_scale_dealt --> crit{"怪物暴击？"}
crit -- 暴击 --> F_crit_hit --> F_amplify
crit -- 不暴击 --> F_amplify
mytk(["自己受到伤害提升%"]) --> F_amplify
F_amplify --> sh{"有护盾？"}
sh -- 没有 --> out(["受到的伤害"])
sh -- 被打穿 --> F_shield_overflow --> out
sh -- 没打穿 --> absorb(["护盾吸收，不掉血"])
'''

_EFFECT_TAIL = '''
mul["单独增伤（幸运三角）"] --> crit{"这段伤害可以暴击？"}
crit -- 暴击 --> F_crit_hit --> bonus
crit -- 不暴击 --> bonus{"这段伤害吃增伤？"}
bonus -- 吃 --> F_amplify__9
bonus -- 不吃 --> out(["追加的伤害"])
F_amplify__9 --> out
'''

_EFFECT = {
    "physical": '''
val(["效果的数值"]) --> F_physical_damage
tdef(["目标防御"]) --> F_def_after_pen
pen(["写了的无视防御%，或者吃穿透时自己的穿透"]) --> F_def_after_pen
F_def_after_pen --> F_physical_mitigation
mylv(["自己等级"]) --> F_physical_mitigation
''' + _LEVEL + '''
F_physical_mitigation --> F_physical_damage
F_level_coef_taken --> F_physical_damage
tred(["目标免伤%"]) --> F_physical_damage
F_physical_damage --> mul
''' + _EFFECT_TAIL,
    "magic": '''
val(["效果的数值"]) --> sub["数值 − 有效法抗"]
tres(["目标法抗"]) --> F_resist_after_pen
mpen(["写了的无视法抗%，或者自己的无视法抗"]) --> F_resist_after_pen
F_resist_after_pen --> sub
''' + _LEVEL + '''
sub --> F_level_reduce
F_level_coef_taken --> F_level_reduce
tred(["目标免伤%"]) --> F_level_reduce
F_level_reduce --> F_amplify
mtk(["目标受到的法术伤害提升%"]) --> F_amplify
F_amplify --> mul
''' + _EFFECT_TAIL,
    "true": '''
val(["效果的数值"]) --> F_level_reduce
''' + _LEVEL + '''
F_level_coef_taken --> F_level_reduce
tred(["目标免伤%"]) --> F_level_reduce
F_level_reduce --> crit{"这段伤害可以暴击？"}
crit -- 暴击 --> F_crit_hit --> out
crit -- 不暴击 --> out(["追加的真实伤害（不吃增伤）"])
''',
}

_KIND_LABELS = {"physical": "物理", "magic": "法术", "true": "真实"}
_TOKEN = re.compile(r"\bF_([^\W\d]\w*?)(?:__(\d+))?(?=\s|$|-)")


def _label(text: str) -> str:
    """Mermaid 方框里的文字：转义会打断语法的字符。"""
    for a, b in (("&", "#amp;"), ('"', "#quot;"), ("<", "#lt;"), (">", "#gt;")):
        text = text.replace(a, b)
    return text


def _title(rules: RuleSet, name: str) -> str:
    formula = rules.formulas.get(name)
    return (formula.title if formula else "") or BATTLE_FORMULAS.get(name) or name


def render(rules: RuleSet, template: str) -> tuple[str, list[str]]:
    """把模板变成 Mermaid 源码，返回（源码，按出现顺序用到的公式代号，含被调用的公式）。"""
    used: list[str] = []
    nodes: dict[str, str] = {}          # 节点编号 → 公式代号
    numbers: dict[str, int] = {}        # 公式代号 → 序号（节点编号用序号，不直接用可能是中文的代号）

    def _node_id(name: str, copy: str | None) -> str:
        number = numbers.setdefault(name, len(numbers) + 1)
        return f"f{number}_{copy or 1}"

    def replace(match: re.Match[str]) -> str:
        name, copy = match.group(1), match.group(2)
        node = _node_id(name, copy)
        if name not in used:
            used.append(name)
        nodes[node] = name
        return node

    body = [_TOKEN.sub(replace, line.strip()) for line in template.strip().splitlines() if line.strip()]
    # 公式里调用的别的公式
    pending = list(used)
    while pending:
        name = pending.pop(0)
        formula = rules.formulas.get(name)
        for callee in sorted(formula.expr.calls) if formula else ():
            node = _node_id(callee, "c")
            if node not in nodes:
                nodes[node] = callee
                body.append(f"{node} -. 被调用 .-> {_node_id(name, None)}")
            if callee not in used:
                used.append(callee)
                pending.append(callee)
    lines = ["flowchart TD"]
    lines += [f'{node}["{_label(_title(rules, name))}"]' for node, name in nodes.items()]
    lines += body
    lines.append("classDef formula fill:#ecf5ff,stroke:#409eff,color:#1f2d3d")
    lines.append("classDef missing fill:#fef0f0,stroke:#f56c6c,color:#c45656")
    ok = [n for n, name in nodes.items() if name in rules.formulas]
    bad = [n for n, name in nodes.items() if name not in rules.formulas]
    if ok:
        lines.append(f"class {','.join(ok)} formula")
    if bad:
        lines.append(f"class {','.join(bad)} missing")
    return "\n".join(lines), used


def damage_flows(rules: RuleSet, item: ItemDef, effect_kinds: set[str]) -> list[tuple[str, str, str, list[str]]]:
    """一件装备相关的伤害计算流程：[(标题, 说明, Mermaid 源码, 用到的公式代号)]。

    武器：按伤害类型画玩家普通攻击；其他部位：画受到怪物攻击（防御、免伤、护盾在这里起作用）；
    再加上装备的效果里追加的每种伤害。
    """
    flows: list[tuple[str, str, str]] = []
    if item.slot == "weapon":
        kind = item.damage_type or "physical"
        if kind == "magic":
            flows.append(("普通攻击（法术）", "法术武器的普通攻击用法力计算，先算法抗再判定闪避和暴击。", _PLAYER_MAGIC))
        elif kind == "precision":
            flows.append(("普通攻击（精准）", "精准武器按物理伤害计算，另外按双方敏捷获得穿透和暴击。",
                          _PLAYER_PHYSICAL + _PRECISION))
        else:
            flows.append(("普通攻击（物理）", "物理武器的普通攻击用攻击力计算。", _PLAYER_PHYSICAL))
    else:
        flows.append(("受到怪物攻击", "防具、饰品上的防御、免伤、闪避、护盾在怪物攻击时起作用。", _TAKEN))
    for kind in ("physical", "magic", "true"):
        if kind in effect_kinds:
            flows.append((f"效果追加的{_KIND_LABELS[kind]}伤害", "套装或装备自带效果里写的追加伤害。", _EFFECT[kind]))
    out = []
    for title, desc, template in flows:
        source, used = render(rules, template)
        out.append((title, desc, source, used))
    return out


def to_models(rules: RuleSet, item: ItemDef, effect_kinds: set[str], ref) -> list[DamageFlow]:
    """ref：公式代号 → FormulaRef（views.formula_ref）。"""
    return [DamageFlow(title=t, description=d, mermaid=m,
                       formulas=[r for r in (ref(rules, n) for n in used) if r is not None],
                       missing=[n for n in used if n not in rules.formulas])
            for t, d, m, used in damage_flows(rules, item, effect_kinds)]
