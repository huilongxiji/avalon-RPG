"""规则版本接口。

查询：列出版本、当前生效版本的概况、重新加载（热更新）、检查单个表达式（网站表达式输入框实时检查用）、
装备卡片列表、装备详情、公式列表（网站"装备与套装""公式"页面用；加 ?draft=true 看草稿里的）。
修改（只改草稿，见 rules/editing.py）：新建/放弃草稿、对比、校验、激活、回滚，装备和公式的增删改。
修改人由 API 后端在 X-Rules-Actor 请求头里带过来（网站本机修改是"网站（本机）"）。
"""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from avalon_contracts.api.rules_admin import (
    EditMeta,
    FormulaRef,
    ItemDetail,
    ItemListResponse,
    StatInfo,
)
from avalon_contracts.common import ApiResponse
from avalon_contracts.errors import GameError
from avalon_contracts.rules.formula import FormulaDef
from avalon_contracts.rules.item import DAMAGE_LABELS, SLOT_LABELS, ItemDef
from avalon_contracts.rules.setting import SettingDef
from avalon_contracts.rules.version import DiffEntry, DraftState, RuleVersionInfo, ValidateResult
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from ..auth import require_internal
from ..engine.expr import ExprError, compile_expr
from ..engine.ruleset import RuleSet
from ..rules import current, editing
from ..rules.explain import Explainer
from ..rules.views import formula_list, formula_ref, item_detail, item_groups

router = APIRouter(prefix="/internal/rules", dependencies=[Depends(require_internal)])


def actor(x_rules_actor: str | None = Header(default=None)) -> str:
    return unquote(x_rules_actor) if x_rules_actor else "未知"


@router.get("/versions", response_model=ApiResponse[list[RuleVersionInfo]])
async def list_versions() -> ApiResponse[list[RuleVersionInfo]]:
    return ApiResponse.success(await editing.versions())


class ExprCheck(BaseModel):
    expr: str
    names: list[str] | None = None
    labels: dict[str, str] = {}          # 变量名 → 中文（显示中文读法用）
    formulas: bool = False               # 能不能调用公式（公式编辑框用；按草稿里的公式检查）


class ExprCheckResult(BaseModel):
    ok: bool
    message: str = ""
    readable: str = ""                   # 中文读法


@router.post("/expr/check", response_model=ApiResponse[ExprCheckResult])
async def expr_check(body: ExprCheck) -> ApiResponse[ExprCheckResult]:
    rules = current.get()
    if body.formulas and await editing.draft_row() is not None:
        _, _, rules = await editing.draft()
    signatures = {name: f.params for name, f in rules.formulas.items()} if body.formulas and rules else None
    try:
        compile_expr(body.expr, set(body.names) if body.names is not None else None, signatures)
    except ExprError as exc:
        return ApiResponse.success(ExprCheckResult(ok=False, message=str(exc)))
    try:
        readable = Explainer(rules, labels=body.labels).expr(body.expr)
    except Exception:   # noqa: BLE001 —— 读法只是辅助显示
        readable = ""
    return ApiResponse.success(ExprCheckResult(ok=True, readable=readable))


class CurrentRules(BaseModel):
    version_id: int | None
    counts: dict[str, int] = {}


def _summary() -> CurrentRules:
    rules = current.get()
    if rules is None:
        return CurrentRules(version_id=None)
    counts = {"items": len(rules.items), "sets": len(rules.sets), "effects": len(rules.effects),
              "monsters": len(rules.monsters), "dungeons": len(rules.dungeons), "props": len(rules.props),
              "recipes": len(rules.recipes), "prop_recipes": len(rules.prop_recipes)}
    return CurrentRules(version_id=rules.version_id, counts=counts)


@router.get("/current", response_model=ApiResponse[CurrentRules])
async def current_rules() -> ApiResponse[CurrentRules]:
    """当前生效的规则版本和各类数据的数量。"""
    return ApiResponse.success(_summary())


@router.post("/reload", response_model=ApiResponse[CurrentRules])
async def reload_rules() -> ApiResponse[CurrentRules]:
    """重新读取规则库里生效的版本（激活新版本之后调用，不用重启）。"""
    await current.reload()
    return ApiResponse.success(_summary())


def _rules() -> RuleSet:
    rules = current.get()
    if rules is None:
        raise GameError("not_found", "规则库尚未初始化，请先导入并激活规则版本")
    return rules


async def _pick(draft: bool) -> RuleSet:
    """draft=true 且有草稿时用草稿，否则用生效版本。"""
    if draft and await editing.draft_row() is not None:
        return (await editing.draft())[2]
    return _rules()


@router.get("/items", response_model=ApiResponse[ItemListResponse])
async def items(draft: bool = False) -> ApiResponse[ItemListResponse]:
    """全部装备，按主套装分组的卡片（一次取回）。看草稿时卡片上标出改过的、新建的。"""
    rules = await _pick(draft)
    if draft and await editing.draft_row() is not None:
        changed, added = await editing.item_marks()
        return ApiResponse.success(item_groups(rules, changed=changed, added=added))
    return ApiResponse.success(item_groups(rules))


@router.get("/items/{item_id}", response_model=ApiResponse[ItemDetail])
async def item(item_id: int, draft: bool = False) -> ApiResponse[ItemDetail]:
    """一件装备的完整参数、所属套装各档位的效果和中文逻辑、伤害计算流程和公式。"""
    rules = await _pick(draft)
    if item_id not in rules.items:
        raise GameError("not_found", f"没有编号为 {item_id} 的装备")
    return ApiResponse.success(item_detail(rules, item_id))


@router.get("/formulas", response_model=ApiResponse[list[FormulaRef]])
async def formulas(draft: bool = False) -> ApiResponse[list[FormulaRef]]:
    """全部公式：中文名称、原式、中文读法、变量说明、调用关系。"""
    return ApiResponse.success(formula_list(await _pick(draft)))


@router.get("/meta", response_model=ApiResponse[EditMeta])
async def meta(draft: bool = False) -> ApiResponse[EditMeta]:
    """编辑表单用：全部属性、部位、伤害类型、套装名。"""
    rules = await _pick(draft)
    return ApiResponse.success(EditMeta(
        version_id=rules.version_id,
        stats=[StatInfo(key=k, name=v.name, percent=v.percent) for k, v in rules.stats.items()],
        slots=dict(SLOT_LABELS), damage_types=dict(DAMAGE_LABELS), sets=list(rules.sets)))


@router.get("/settings", response_model=ApiResponse[list[SettingDef]])
async def settings(draft: bool = False) -> ApiResponse[list[SettingDef]]:
    from ..rules.game_defaults import DEFAULTS, LABELS

    rules = await _pick(draft)
    return ApiResponse.success([
        SettingDef(key=k, value=rules.setting(k, v), description=LABELS.get(k, k))
        for k, v in DEFAULTS.items()
    ])


@router.put("/draft/settings/{key}", response_model=ApiResponse[SettingDef])
async def update_setting(key: str, body: SettingDef, who: str = Depends(actor)) -> ApiResponse[SettingDef]:
    return ApiResponse.success(await editing.save_setting(key, body, actor=who))


@router.put('/draft/settings', response_model=ApiResponse[list[SettingDef]])
async def update_settings(body: list[SettingDef], who: str = Depends(actor)):
    return ApiResponse.success(await editing.save_settings(body, actor=who))


# ---------------------------------------------------------------- 草稿


@router.get("/draft", response_model=ApiResponse[DraftState])
async def draft_state() -> ApiResponse[DraftState]:
    return ApiResponse.success(DraftState(**await editing.state()))


class DraftNote(BaseModel):
    note: str = ""


@router.post("/draft", response_model=ApiResponse[RuleVersionInfo])
async def create_draft(body: DraftNote, who: str = Depends(actor)) -> ApiResponse[RuleVersionInfo]:
    """新建草稿：整份复制当前生效版本。"""
    return ApiResponse.success(await editing.create_draft(actor=who, note=body.note))


@router.delete("/draft", response_model=ApiResponse[None])
async def discard_draft(who: str = Depends(actor)) -> ApiResponse[None]:
    await editing.discard_draft(actor=who)
    return ApiResponse.success(None)


@router.get("/draft/diff", response_model=ApiResponse[list[DiffEntry]])
async def draft_diff() -> ApiResponse[list[DiffEntry]]:
    return ApiResponse.success(await editing.draft_diff())


@router.post("/draft/validate", response_model=ApiResponse[ValidateResult])
async def validate() -> ApiResponse[ValidateResult]:
    return ApiResponse.success(await editing.validate())


@router.post("/draft/activate", response_model=ApiResponse[RuleVersionInfo])
async def activate(who: str = Depends(actor)) -> ApiResponse[RuleVersionInfo]:
    """校验通过后激活草稿，马上热更新。"""
    return ApiResponse.success(await editing.activate_draft(actor=who))


@router.post("/versions/{version_id}/rollback", response_model=ApiResponse[RuleVersionInfo])
async def rollback(version_id: int, who: str = Depends(actor)) -> ApiResponse[RuleVersionInfo]:
    return ApiResponse.success(await editing.rollback(version_id, actor=who))


# ---------------------------------------------------------------- 草稿里的装备、公式


async def _item_out(item_id: int) -> ItemDetail:
    return item_detail((await editing.draft())[2], item_id)


@router.post("/draft/items", response_model=ApiResponse[ItemDetail])
async def create_item(body: ItemDef, who: str = Depends(actor)) -> ApiResponse[ItemDetail]:
    """新建装备（编号自动分配，body 里的 id 不用填）。"""
    saved = await editing.save_item(None, body, actor=who)
    return ApiResponse.success(await _item_out(saved.id))


@router.put("/draft/items/{item_id}", response_model=ApiResponse[ItemDetail])
async def update_item(item_id: int, body: ItemDef, who: str = Depends(actor)) -> ApiResponse[ItemDetail]:
    saved = await editing.save_item(item_id, body, actor=who)
    return ApiResponse.success(await _item_out(saved.id))


@router.delete("/draft/items/{item_id}", response_model=ApiResponse[None])
async def delete_item(item_id: int, who: str = Depends(actor)) -> ApiResponse[None]:
    await editing.delete_item(item_id, actor=who)
    return ApiResponse.success(None)


async def _formula_out(name: str) -> Any:
    return formula_ref((await editing.draft())[2], name)


@router.post("/draft/formulas", response_model=ApiResponse[FormulaRef])
async def create_formula(body: FormulaDef, who: str = Depends(actor)) -> ApiResponse[FormulaRef]:
    saved = await editing.save_formula(None, body, actor=who)
    return ApiResponse.success(await _formula_out(saved.name))


@router.put("/draft/formulas/{name}", response_model=ApiResponse[FormulaRef])
async def update_formula(name: str, body: FormulaDef, who: str = Depends(actor)) -> ApiResponse[FormulaRef]:
    saved = await editing.save_formula(name, body, actor=who)
    return ApiResponse.success(await _formula_out(saved.name))


@router.delete("/draft/formulas/{name}", response_model=ApiResponse[None])
async def delete_formula(name: str, who: str = Depends(actor)) -> ApiResponse[None]:
    await editing.delete_formula(name, actor=who)
    return ApiResponse.success(None)
