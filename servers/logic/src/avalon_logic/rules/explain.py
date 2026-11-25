"""把表达式和效果逻辑翻译成中文，给网站的装备详情、效果编辑器显示用。

例如::

    self.agi * agi_dmg_pct // 100            → ⌊自己的敏捷 × 60 ÷ 100⌋
    not hit.dodged and hit.damage > 0        → 没有被闪避 且 这次攻击的伤害 > 0
    after_attack + 概率 66 + 叠层 + 伤害       → 【攻击结算后】如果……，有 66% 概率：① 给目标叠加 1 层碎晶 ② ……

只做显示，不参与计算；表达式在提交规则时已经检查过，这里遇到看不懂的写法就原样显示。
"""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping
from typing import Any

from avalon_contracts.rules.effect import (
    BATTLE_OPS,
    TRIGGERS,
    ActionSpec,
    AuraMod,
    EffectDef,
    StaticMod,
    TriggerSpec,
    format_number,
)

from ..engine.ruleset import RuleSet

_BIN = {ast.Add: "+", ast.Sub: "-", ast.Mult: "×", ast.Div: "÷", ast.Mod: "除以后的余数", ast.Pow: "的次方"}
_PREC = {ast.Add: 1, ast.Sub: 1, ast.Mult: 2, ast.Div: 2, ast.FloorDiv: 2, ast.Mod: 2, ast.Pow: 3}
_CMP = {ast.Gt: ">", ast.GtE: "≥", ast.Lt: "<", ast.LtE: "≤", ast.Eq: "=", ast.NotEq: "≠"}
_FUNCS = {"min": "较小值", "max": "较大值", "abs": "绝对值", "floor": "向下取整", "ceil": "向上取整",
          "round": "四舍五入", "sqrt": "开方", "exp": "e的次方", "clamp": "限制在范围内"}
_FIGHTER = {"hp_now": "当前生命", "hp_max": "最大生命", "shield": "护盾", "level": "等级",
            "is_player": "是玩家", "is_world_boss": "是世界BOSS"}
# (正面说法, 加"不"之后的说法)
_FIELDS: dict[str, dict[str, tuple[str, str]]] = {
    "hit": {"damage": ("这次攻击的伤害", ""), "crit": ("暴击了", "没有暴击"), "dodged": ("被闪避", "没有被闪避"),
            "magic": ("是法术攻击", "不是法术攻击"), "physical": ("是物理攻击", "不是物理攻击"),
            "precision": ("是精准攻击", "不是精准攻击"), "saved": ("免疫了致命伤害", "没有免疫致命伤害"),
            "multi": ("是多段攻击", "不是多段攻击"), "true_part": ("这次攻击里的真实伤害", ""),
            "precision_crit_dmg": ("精准武器额外的暴击伤害", "")},
    "seg": {"damage": ("这一段的伤害", ""), "kind_magic": ("这一段是法术伤害", "这一段不是法术伤害"),
            "chase": ("这一段是追击", "这一段不是追击")},
    "dealt": {"amount": ("这次造成的伤害", ""), "attack": ("是普通攻击造成的", "不是普通攻击造成的")},
    "stack": {"count": ("当前层数", ""), "adding": ("这次增加的层数", ""), "max": ("层数上限", "")},
    "last": {"prevented": ("上一个叠层被取消了", "上一个叠层没有被取消"), "count": ("上一个追击的段数", ""),
             "damage": ("上一个伤害动作造成的伤害", "")},
    "weapon": {"magic": ("使用法术武器", "不是法术武器"), "physical": ("使用物理武器", "不是物理武器"),
               "precision": ("使用精准武器", "不是精准武器"), "id": ("武器编号", "")},
}
DAMAGE_LABELS = {"physical": "物理", "magic": "法术", "true": "真实"}


class Explainer:
    """labels：变量名 → 中文（属性名、层数名、公式变量说明）；params：参数名 → 数值（直接显示数值）。"""

    def __init__(self, rules: RuleSet | None = None, *, params: Mapping[str, Any] | None = None,
                 labels: Mapping[str, str] | None = None) -> None:
        self.stats = {k: v.name for k, v in rules.stats.items()} if rules else {}
        self.percent = {k for k, v in rules.stats.items() if v.percent} if rules else set()
        self.stacks = {k: v.name for k, v in rules.stacks.items()} if rules else {}
        self.effects = {k: v.name for k, v in rules.effects.items()} if rules else {}
        self.items = {str(k): v.name for k, v in rules.items.items()} if rules else {}
        self.formulas = {k: (v.title or k) for k, v in rules.formulas.items()} if rules else {}
        self.params = dict(params or {})
        self.labels = dict(labels or {})

    # ---- 表达式

    def expr(self, source: Any) -> str:
        if not isinstance(source, str):
            return format_number(source)
        try:
            tree = ast.parse(source.strip(), mode="eval")
            return self._node(tree.body)
        except (SyntaxError, ValueError, KeyError):
            return source

    def _weapon_is(self, node: ast.Compare) -> str | None:
        """weapon.id == 编号 → 武器是「装备名」。"""
        if (len(node.ops) == 1 and isinstance(node.ops[0], (ast.Eq, ast.NotEq))
                and isinstance(node.left, ast.Attribute) and isinstance(node.comparators[0], ast.Constant)):
            try:
                path = self._path(node.left)
            except ValueError:
                return None
            if path == ["weapon", "id"]:
                value = node.comparators[0].value
                name = self.items.get(str(int(value)) if isinstance(value, (int, float)) else str(value), str(value))
                return f"武器{'是' if isinstance(node.ops[0], ast.Eq) else '不是'}「{name}」"
        return None

    def _path(self, node: ast.AST) -> list[str]:
        parts: list[str] = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if not isinstance(node, ast.Name):
            raise ValueError
        parts.append(node.id)
        return parts[::-1]

    def _name(self, path: list[str], negate: bool = False) -> str:
        root, rest = path[0], path[1:]
        if not rest:
            if root in self.params:
                return format_number(self.params[root])
            if root in self.labels:
                return self.labels[root]
            return {"round_no": "当前回合", "pieces": "套装件数",
                    "entry": "这场触发了战斗开始（爬塔的后续战斗不算）"}.get(root, root)
        if root in ("self", "foe"):
            who = "自己的" if root == "self" else "目标的"
            head = rest[0]
            if head in ("panel", "base") and len(rest) == 2:
                return f"{who}{'面板' if head == 'panel' else '基础'}{self.stats.get(rest[1], rest[1])}"
            if head == "stacks" and len(rest) == 2:
                return f"{who}{self.stacks.get(rest[1], rest[1])}层数"
            if head == "vars" and len(rest) == 2:
                return f"「{rest[1]}」"
            if head in ("is_player", "is_world_boss"):
                what = "玩家" if head == "is_player" else "世界BOSS"
                return f"{who[:-1]}{'不是' if negate else '是'}{what}"
            return who + self.stats.get(head, _FIGHTER.get(head, head))
        if root == "dealt" and rest[0] == "by" and len(rest) == 2:
            name = self.effects.get(rest[1], rest[1])
            return f"不是由「{name}」造成的" if negate else f"由「{name}」造成的"
        if root == "hit" and rest[0] == "by" and len(rest) == 2:
            name = self.effects.get(rest[1], rest[1])
            return f"这次普通攻击不是「{name}」换成的" if negate else f"这次普通攻击是「{name}」换成的"
        field = _FIELDS.get(root, {}).get(rest[0])
        if field:
            return field[1] if negate and field[1] else field[0]
        return ".".join(path)

    def _wrap(self, node: ast.AST, parent: int) -> str:
        text = self._node(node)
        if isinstance(node, ast.BinOp) and _PREC.get(type(node.op), 9) < parent:
            return f"({text})"
        if isinstance(node, (ast.BoolOp, ast.IfExp, ast.Compare)):
            return f"({text})"
        return text

    def _node(self, node: ast.AST) -> str:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return "是" if node.value else "否"
            return format_number(node.value)
        if isinstance(node, (ast.Name, ast.Attribute)):
            return self._name(self._path(node))
        if isinstance(node, ast.BinOp):
            prec = _PREC.get(type(node.op), 9)
            left, right = self._wrap(node.left, prec), self._wrap(node.right, prec + 1)
            if isinstance(node.op, ast.FloorDiv):
                return f"⌊{self._wrap(node.left, 2)} ÷ {self._wrap(node.right, 3)}⌋"
            if isinstance(node.op, ast.Mod):
                return f"{self._wrap(node.left, 2)} 除以 {self._wrap(node.right, 3)} 的余数"
            return f"{left} {_BIN.get(type(node.op), '?')} {right}"
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                inner = node.operand
                if isinstance(inner, (ast.Name, ast.Attribute)):
                    path = self._path(inner)
                    negated = self._name(path, negate=True)
                    if negated != self._name(path):
                        return negated
                return f"并非 {self._wrap(inner, 9)}"
            sign = "-" if isinstance(node.op, ast.USub) else "+"
            return sign + self._wrap(node.operand, 9)
        if isinstance(node, ast.BoolOp):
            joiner = " 且 " if isinstance(node.op, ast.And) else " 或 "
            return joiner.join(self._wrap(v, 9) if isinstance(v, ast.BoolOp) else self._node(v)
                               for v in node.values)
        if isinstance(node, ast.Compare):
            weapon = self._weapon_is(node)
            if weapon:
                return weapon
            parts = [self._wrap(node.left, 0)]
            for op, right in zip(node.ops, node.comparators, strict=True):
                parts += [_CMP.get(type(op), "?"), self._wrap(right, 0)]
            return " ".join(parts)
        if isinstance(node, ast.IfExp):
            return f"如果 {self._node(node.test)} 则 {self._node(node.body)}，否则 {self._node(node.orelse)}"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            parts = [self._node(a) for a in node.args]
            parts += [f"{self.labels.get(k.arg, k.arg)}={self._node(k.value)}" for k in node.keywords]
            if node.func.id in self.formulas:
                return f"「{self.formulas[node.func.id]}」({'，'.join(parts)})"
            return f"{_FUNCS.get(node.func.id, node.func.id)}({'，'.join(parts)})"
        raise ValueError

    # ---- 效果

    def _who(self, target: str | None, default: str) -> str:
        return "自己" if (target or default) == "self" else "目标"

    def stat_change(self, target: str | None, default: str, stat: str, op: str, value: Any,
                    rounds: Any = None, scope: str = "battle") -> str:
        who = self._who(target, default)
        name = self.stats.get(stat, stat)
        v = self.expr(value)
        if scope == "panel":
            verb = {"add": f"增加 {v}", "mul": f"乘以 {v}", "set": f"设为 {v}"}.get(op, f"{op} {v}")
            text = f"{who}的面板{name}{verb}"
        else:
            unit = "%" if stat in self.percent else ""
            verb = {"add": f"增加 {v}{unit}", "add_base_pct": f"增加基础值的 {v}%", "down": f"减少 {v}{unit}",
                    "down_pct": f"降低 {v}%", "down_pct_each": f"再单独降低 {v}%",
                    "mul_pct": f"提升 {v}%"}.get(op, f"{BATTLE_OPS.get(op, op)} {v}")
            text = f"{who}的{name}{verb}"
        if rounds is not None:
            text += f"，持续 {self.expr(rounds)} 回合"
        return text

    def action(self, spec: ActionSpec | Mapping[str, Any], on: str | None = None) -> str:
        if not isinstance(spec, ActionSpec):
            spec = ActionSpec.model_validate(spec)
        a = spec.args()
        kind = spec.action
        if kind == "modify_stat":
            text = self.stat_change(a.get("target"), "self", a.get("stat", ""), a.get("op", "add"),
                                    a.get("value"), a.get("rounds"), a.get("scope", "battle"))
        elif kind == "damage":
            text = (f"对{self._who(a.get('target'), 'foe')}造成{DAMAGE_LABELS.get(a.get('kind'), '')}伤害"
                    f" {self.expr(a.get('value'))}")
            extras = [x for x, on in (("吃穿透", a.get("pen")), ("可以暴击", a.get("can_crit")),
                                      ("吃增伤", a.get("bonus"))) if on]
            if extras:
                text += f"（{'、'.join(extras)}）"
            ignores = [f"{name} {self.expr(a[key])}%" for key, name in (("ignore_def", "只无视防御"),
                                                                         ("ignore_resist", "只无视法抗"))
                       if a.get(key) is not None]
            if ignores:
                text += f"（{'、'.join(ignores)}，不用自己的穿透）"
            if a.get("not_lowered_by"):
                names = "、".join(self.effects.get(x, x) for x in a["not_lowered_by"])
                text += f"（算目标防御和法抗时不计入{names}造成的降低）"
            if a.get("base_def"):
                text += "（按目标的基础防御算，不计入各种减防）"
            if a.get("label"):
                text += f"，战报显示为「{a['label']}」"
        elif kind == "replace_hit":
            names = {"physical": "物理伤害", "magic": "法术伤害", "true": "真实伤害"}
            hits = a.get("hits") or []
            parts = [f"{names.get(h.get('kind'), '')} {self.expr(h.get('value'))}" for h in hits]
            if len(parts) > 1 and len(set(parts)) == 1:
                text = f"这次普通攻击换成 {len(parts)} 段攻击，每段造成{parts[0]}"
            elif len(parts) > 1:
                text = "这次普通攻击换成 " + str(len(parts)) + " 段攻击：" + "；".join(
                    f"第 {i + 1} 段造成{p}" for i, p in enumerate(parts))
            else:
                text = f"这次普通攻击改为造成{parts[0] if parts else ''}"
            if len(parts) > 1:
                text += "（每段单独判定闪避和暴击）"
            text += "（多个效果都改普通攻击时，优先级小的生效）"
        elif kind == "scale_hit":
            base = a.get("base")
            amount = (f"{self.expr(a.get('value'))}%" if base is None
                      else f"（{self.expr(a.get('value'))}）÷ {self.expr(base)}")
            text = f"这次攻击（多段攻击时是这一段）的伤害提升至 {amount}"
            text += "（连真实伤害一起提升）" if a.get("with_true") else "（真实伤害不提升）"
            if a.get("at_least_1"):
                text += "，至少 1 点"
        elif kind == "chase":
            text = (f"追击：以 {self.expr(a.get('base'))} 为基数，第一次造成 {self.expr(a.get('pct'))}%，"
                    f"本回合每追击一次降低 {self.expr(a.get('decay'))}%；每段按 {self.expr(a.get('crit_rate'))}% "
                    f"判定暴击（暴击伤害 {self.expr(a.get('crit_dmg'))}%），暴击了就再追击一次")
        elif kind == "execute":
            text = f"斩杀{self._who(a.get('target'), 'foe')}（生命直接降到 0）"
        elif kind == "lose_hp":
            text = f"自己扣除生命 {self.expr(a.get('value'))}（不算受到伤害，最低保留 1 点）"
        elif kind == "reduce_hit":
            text = f"这次受到的伤害减少 {self.expr(a.get('value'))}"
        elif kind == "set_hit":
            part = {"physical": "物理伤害", "magic": "法术伤害", "true": "真实伤害"}.get(a.get("part"), "")
            text = f"这次攻击追加{part} {self.expr(a.get('value'))}"
            if a.get("part") == "true":
                text += "（和其他追加的真实伤害加在一起结算）"
            else:
                text += "（并入这次攻击，一起吃增伤）"
        elif kind == "heal":
            text = f"{self._who(a.get('target'), 'self')}回复生命 {self.expr(a.get('value'))}"
        elif kind == "shield":
            text = f"{self._who(a.get('target'), 'self')}获得护盾 {self.expr(a.get('value'))}"
        elif kind == "stack":
            name = self.stacks.get(a.get("name"), a.get("name"))
            who = self._who(a.get("target"), "foe")
            op = a.get("op", "add")
            v = self.expr(a.get("value", 1))
            text = {"add": f"给{who}叠加 {v} 层{name}", "remove": f"{who}的{name}减少 {v} 层",
                    "clear": f"清空{who}的{name}", "set": f"{who}的{name}设为 {v} 层"}.get(op, op)
        elif kind == "prevent":
            text = "取消这次叠层" if on == "stack_full" else "取消这次事件"
        elif kind in ("flag", "carry"):
            text = f"记录「{a.get('name')}」= {self.expr(a.get('value', 1))}"
            if kind == "carry" or a.get("carry"):
                text += "（爬塔连战时跨场保留）"
        elif kind == "note":
            text = f"战报写入：{EffectDef(id='x', name='x', desc=str(a.get('text', '')), params=self.params).render_desc()}"
        elif kind == "random":
            options = [f"{o.get('label', '')}：" + "；".join(self.action(x, on) for x in o.get("do", []))
                       for o in a.get("choices", [])]
            weights = [self.params.get(w) if isinstance(w, str) else w
                       for w in (o.get("weight") for o in a.get("choices", []))]
            if weights and all(isinstance(w, (int, float)) and w > 0 for w in weights):
                total = sum(weights)
                options = [f"{w * 100 / total:g}% 概率{o}" for w, o in zip(weights, options, strict=True)]
            text = "随机选一项执行 —— " + " ／ ".join(options)
        else:
            text = kind
        if spec.if_:
            text = f"（如果 {self.expr(spec.if_)}）{text}"
        return text

    def trigger(self, spec: TriggerSpec) -> str:
        # 去掉时机名称里给编辑器看的提示（括号部分）
        head = f"【{re.sub(r'（.*?）', '', TRIGGERS.get(spec.on, spec.on))}】"
        if spec.stack:
            head += f"（{self.stacks.get(spec.stack, spec.stack)}）"
        conds = []
        if spec.if_:
            conds.append(f"如果 {self.expr(spec.if_)}")
        if spec.chance is not None:
            conds.append(f"有 {self.expr(spec.chance)}% 概率")
        limits = []
        if spec.once == "battle":
            limits.append("每场战斗只触发一次")
        elif spec.once == "run":
            limits.append("每次挑战只触发一次")
        if spec.cooldown:
            limits.append(f"冷却 {spec.cooldown} 回合")
        circled = "①②③④⑤⑥⑦⑧⑨⑩"
        steps = " ".join(f"{circled[i] if i < len(circled) else i + 1} {self.action(a, spec.on)}"
                         for i, a in enumerate(spec.do))
        text = head + "，".join(conds) + ("：" if conds else "") + steps
        if limits:
            text += f"（{'，'.join(limits)}）"
        return text

    def static(self, mod: StaticMod) -> str:
        scope = "panel" if mod.op in ("mul", "set") else "battle"
        op = "add" if mod.op == "max" else mod.op
        text = "汇总面板时：" + self.stat_change("self", "self", mod.stat, op, mod.value, scope=scope)
        if mod.op == "add_pct":
            text = f"汇总面板时：自己的{self.stats.get(mod.stat, mod.stat)}加成 {self.expr(mod.value)}%"
        elif mod.op == "max":
            unit = "%" if mod.stat in self.percent else ""
            text = (f"汇总面板时：自己的{self.stats.get(mod.stat, mod.stat)}增加 {self.expr(mod.value)}{unit}"
                    "（多个套装都有时只取最大的一个）")
        if mod.if_:
            text += f"（条件：{self.expr(mod.if_)}）"
        return text

    def aura(self, aura: AuraMod) -> str:
        text = "战斗中一直生效：" + self.stat_change(aura.target, "self", aura.stat, aura.op, aura.value)
        if aura.if_:
            text += f"（条件：{self.expr(aura.if_)}）"
        return text

    def effect_lines(self, effect: EffectDef) -> list[str]:
        return ([self.static(m) for m in effect.static] + [self.aura(a) for a in effect.auras]
                + [self.trigger(t) for t in effect.triggers])
