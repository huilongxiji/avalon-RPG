"""编辑器对动作扩展字段的结构检查；表达式和枚举由规则编译器检查。"""

from avalon_contracts.errors import GameError
from avalon_contracts.rules.effect import ActionSpec
from pydantic import ValidationError

FIELDS = {
    "modify_stat": "target scope stat op value rounds",
    "damage": "target kind value ignore_def ignore_resist crit_rate crit_dmg pen can_crit bonus not_lowered_by base_def label",
    "replace_hit": "hits multi",
    "set_hit": "part value",
    "scale_hit": "value base with_true at_least_1",
    "reduce_hit": "value",
    "chase": "base pct decay crit_rate crit_dmg counter label",
    "execute": "target label",
    "lose_hp": "value",
    "heal": "target value",
    "shield": "target value",
    "stack": "name op target value",
    "prevent": "",
    "flag": "name value carry",
    "carry": "name value",
    "note": "text",
    "random": "choices",
}
STRINGS = {"target", "scope", "stat", "op", "kind", "part", "name", "counter", "label", "text"}
BOOLEANS = {"pen", "can_crit", "bonus", "base_def", "multi", "at_least_1", "with_true", "carry"}


def check_action(action: ActionSpec, path: str, depth: int = 0) -> None:
    def fail(message: str):
        raise GameError("invalid", f"{path}：{message}")

    if depth > 16:
        fail("随机动作嵌套超过 16 层，请拆分效果")
    allowed = set(FIELDS.get(action.action, "").split())
    args = action.args()
    if extra := args.keys() - allowed:
        fail(f"未知动作参数：{'、'.join(sorted(extra))}")
    for key, value in args.items():
        if key in STRINGS and not isinstance(value, str):
            fail(f"{key} 必须是文字")
        if key in BOOLEANS and not isinstance(value, bool):
            fail(f"{key} 必须是 true 或 false")
    if action.action == "replace_hit":
        hits = args.get("hits")
        if not isinstance(hits, list) or not hits:
            fail("hits 至少要有一段攻击")
        for hit in hits:
            if not isinstance(hit, dict) or set(hit) != {"kind", "value"} or not isinstance(hit["kind"], str):
                fail("每段攻击须包含 kind（文字）和 value（数值或表达式）")
    if action.action == "random":
        choices = args.get("choices")
        if not isinstance(choices, list) or not choices:
            fail("choices 至少要有一个选项")
        for index, choice in enumerate(choices, 1):
            if not isinstance(choice, dict) or set(choice) - {"label", "do", "weight"}:
                fail(f"选项 {index} 只能填写 label、do、weight")
            if "label" in choice and not isinstance(choice["label"], str):
                fail(f"选项 {index} 的 label 必须是文字")
            actions = choice.get("do")
            if not isinstance(actions, list) or not actions:
                fail(f"选项 {index} 的 do 必须是非空动作列表")
            for number, raw in enumerate(actions, 1):
                try:
                    nested = ActionSpec.model_validate(raw)
                except ValidationError as exc:
                    fail(f"选项 {index} 的动作 {number} 格式不正确：{exc.errors(include_input=False)[0]['msg']}")
                check_action(nested, f"{path} / 选项 {index} / 动作 {number}", depth + 1)
