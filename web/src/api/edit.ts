// 修改规则：草稿、对比、校验、激活、回滚，草稿里的装备和公式。
// 权限由网站账号角色决定，后端统一校验。
import { h } from 'vue'
import { ElMessageBox } from 'element-plus'
import { request, RequestError } from './client'
import type { FormulaDef, FormulaRef, ItemDef, ItemDetail } from './catalog'

export interface VersionInfo {
  id: number
  parent_id: number | null
  status: 'draft' | 'active' | 'archived' | 'discarded'
  note: string
  created_by: string
  created_at: string | null
  activated_at: string | null
}

export interface DraftState {
  active: VersionInfo | null
  draft: VersionInfo | null
  changes: number
  editable: boolean
  publishable: boolean
}

export interface DiffEntry {
  category: string
  category_label: string
  key: string
  name: string
  change: 'added' | 'removed' | 'changed'
  details: string[]
}

export interface ValidateResult {
  ok: boolean
  problems: string[]
  battles: number
}

export interface ExprCheckResult {
  ok: boolean
  message: string
  readable: string
}

export const STATUS_LABELS: Record<VersionInfo['status'], string> = {
  draft: '草稿',
  active: '生效中',
  archived: '已归档',
  discarded: '已放弃',
}

const E = '/api/v1/edit'
const json = (body: unknown) => ({ body: JSON.stringify(body) })

export const fetchDraftState = () => request<DraftState>(`${E}/draft`)
export const fetchVersions = () => request<VersionInfo[]>(`${E}/versions`)
export const createDraft = (note = '') => request<VersionInfo>(`${E}/draft`, { method: 'POST', ...json({ note }) })
export const discardDraft = () => request<null>(`${E}/draft`, { method: 'DELETE' })
export const fetchDiff = () => request<DiffEntry[]>(`${E}/draft/diff`)
export const validateDraft = () => request<ValidateResult>(`${E}/draft/validate`, { method: 'POST' })
export const activateDraft = () => request<VersionInfo>(`${E}/draft/activate`, { method: 'POST' })
export const rollbackTo = (id: number) => request<VersionInfo>(`${E}/versions/${id}/rollback`, { method: 'POST' })

export const createItem = (item: ItemDef) =>
  request<ItemDetail>(`${E}/draft/items`, { method: 'POST', ...json(item) })
export const updateItem = (id: number, item: ItemDef) =>
  request<ItemDetail>(`${E}/draft/items/${id}`, { method: 'PUT', ...json(item) })
export const deleteItem = (id: number) => request<null>(`${E}/draft/items/${id}`, { method: 'DELETE' })

export const createFormula = (f: FormulaDef) =>
  request<FormulaRef>(`${E}/draft/formulas`, { method: 'POST', ...json(f) })
export const updateFormula = (name: string, f: FormulaDef) =>
  request<FormulaRef>(`${E}/draft/formulas/${encodeURIComponent(name)}`, { method: 'PUT', ...json(f) })
export const deleteFormula = (name: string) =>
  request<null>(`${E}/draft/formulas/${encodeURIComponent(name)}`, { method: 'DELETE' })

export const checkExpr = (body: { expr: string; names?: string[]; labels?: Record<string, string>; formulas?: boolean }) =>
  request<ExprCheckResult>(`${E}/expr/check`, { method: 'POST', ...json(body) })

/** 弹窗显示错误；规则校验没通过时把全部问题逐条列出来 */
export function showProblems(title: string, message: string, problems: string[] = []) {
  const body = problems.length
    ? h('div', [
        h('p', { style: 'margin:0 0 8px' }, message),
        h('ol', { style: 'margin:0;padding-left:20px;line-height:1.7;max-height:50vh;overflow:auto' },
          problems.map((p) => h('li', p))),
      ])
    : message
  return ElMessageBox.alert(body, title, { type: 'error', confirmButtonText: '知道了' }).catch(() => undefined)
}

export function showError(e: unknown, title = '没有保存') {
  if (e instanceof RequestError) return showProblems(title, e.message, e.problems)
  return showProblems(title, (e as Error).message)
}
