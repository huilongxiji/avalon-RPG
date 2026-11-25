// 规则数据查询：装备卡片、装备详情、公式。数据格式见 avalon_contracts/api/rules_admin.py
// draft 为 true 时看草稿里的内容（没有草稿时后端自动用生效版本）
import { request } from './client'

export interface StatValue {
  key: string
  name: string
  value: number
  percent: boolean
}

export interface SetRef {
  name: string
  role: 'main' | 'secondary'
}

export interface EffectBrief {
  id: string
  name: string
  desc: string
}

export interface TierBrief {
  pieces: number
  effects: EffectBrief[]
}

export interface SetSummary {
  name: string
  tiers: TierBrief[]
  item_count: number
}

export interface ItemCard {
  id: number
  name: string
  slot: string
  slot_label: string
  damage_type: string | null
  damage_label: string | null
  price: number
  main_stats: StatValue[]
  extra_stats: StatValue[]
  sets: SetRef[]
  effect_brief: string
  changed: boolean
  added: boolean
  retired: boolean
  problems: number
}

export interface ItemGroup {
  set: SetSummary | null
  items: ItemCard[]
}

export interface ItemListResponse {
  version_id: number | null
  groups: ItemGroup[]
  total: number
}

export interface ExprDetail {
  where: string
  source: string
  readable: string
}

export interface EffectDetail {
  id: string
  name: string
  desc: string
  template: string
  params: Record<string, number>
  logic: string[]
  expressions: ExprDetail[]
}

export interface TierDetail {
  pieces: number
  effects: EffectDetail[]
}

export interface SetDetail {
  name: string
  role: 'main' | 'secondary'
  tiers: TierDetail[]
  members: string[]
}

export interface FormulaRef {
  name: string
  title: string
  description: string
  expr: string
  readable: string
  variables: Record<string, string>
  required: boolean
  calls: string[]
  used_by: string[]
}

export interface FormulaDef {
  name: string
  title: string
  expr: string
  params: Record<string, string>
  description: string
}

export interface DamageFlow {
  title: string
  description: string
  mermaid: string
  formulas: FormulaRef[]
  missing: string[]
}

export interface StatInfo {
  key: string
  name: string
  percent: boolean
}

export interface EditMeta {
  version_id: number | null
  stats: StatInfo[]
  slots: Record<string, string>
  damage_types: Record<string, string>
  sets: string[]
}

export interface ItemDef {
  id: number
  name: string
  slot: string
  price: number
  stats: Record<string, number>
  damage_type: string | null
  sets: string[]
  effects: string[]
  sponsor: boolean
  retired: boolean
}

export interface ItemDetail {
  item: ItemDef
  slot_label: string
  stats: StatValue[]
  sets: SetDetail[]
  own_effects: EffectDetail[]
  formulas: FormulaRef[]
  flows: DamageFlow[]
  notes: string[]
}

export const DAMAGE_LABELS: Record<string, string> = { physical: '物理', magic: '法术', precision: '精准' }

const q = (draft: boolean) => (draft ? '?draft=true' : '')

export function fetchItems(draft = false): Promise<ItemListResponse> {
  return request<ItemListResponse>(`/api/v1/catalog/items${q(draft)}`)
}

export function fetchItem(id: number, draft = false): Promise<ItemDetail> {
  return request<ItemDetail>(`/api/v1/catalog/items/${id}${q(draft)}`)
}

export function fetchFormulas(draft = false): Promise<FormulaRef[]> {
  return request<FormulaRef[]>(`/api/v1/catalog/formulas${q(draft)}`)
}

export function fetchMeta(draft = false): Promise<EditMeta> {
  return request<EditMeta>(`/api/v1/catalog/meta${q(draft)}`)
}

/** 属性数值的显示：百分比属性加 %，整数不带小数 */
export function formatStat(s: StatValue): string {
  const v = Number.isInteger(s.value) ? String(s.value) : s.value.toFixed(1)
  return s.percent ? `${v}%` : v
}
