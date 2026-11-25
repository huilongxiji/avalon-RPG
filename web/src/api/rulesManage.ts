import { request } from './client'
import type { StatInfo } from './catalog'

export type Category = 'effects' | 'sets' | 'monsters' | 'dungeons' | 'drops' | 'props' | 'recipes' | 'prop_recipes' | 'stacks'
// 规则文档支持动作扩展字段和 JSON 编辑，字段合法性由共享模型及服务端完整编译校验。
export type RuleDocument = Record<string, any>
export interface RuleRecord {
  key: string; name: string; summary: string; data: RuleDocument; hash: string
  references: string[]; protected_reason: string
}
export interface RuleRecords { version_id: number; draft: boolean; records: RuleRecord[] }
export interface Choice { key: string; name: string; kind?: string }
export interface RuleCheck { ok: boolean; message: string; data: RuleDocument; preview?: { description: string; logic: string[] } }
export interface ManageMeta {
  version_id: number; draft: boolean; stats: StatInfo[]
  effects: Choice[]; sets: Choice[]; monsters: Choice[]; dungeons: Choice[]; items: Choice[]; props: Choice[]; stacks: Choice[]
  triggers: Record<string, string>; actions: Record<string, string>; static_ops: Record<string, string>
  battle_ops: Record<string, string>; kinds: Record<string, string>; prop_effects: Record<string, string>
  next_ids: Record<string, number>; schemas: Record<string, RuleDocument>
}
export const TITLES: Record<Category, string> = {
  effects: '效果', sets: '套装', monsters: '怪物', dungeons: '副本', drops: '掉落',
  props: '道具', recipes: '装备配方', prop_recipes: '道具配方', stacks: '层数',
}
export const HELP: Record<Category, string> = {
  effects: '定义静态加成、持续效果和触发动作，再将效果关联到装备、套装或怪物。',
  sets: '按装备件数配置套装档位。每个档位可关联多个效果。',
  monsters: '配置属性、战斗效果和击败奖励；掉落也可在“掉落管理”中集中编辑。',
  dungeons: '配置体力消耗、遇怪权重和隐秘怪物。权重用于相对抽取，不要求合计为 100。',
  drops: '各项掉落概率独立计算，不要求合计为 100%。归属装备也参与 BOSS 自选与分解归属判断。',
  props: '配置道具用途、数值和礼盒来源。曾发布的道具保留定义，避免玩家仓库中的物品失效。',
  recipes: '配置使用背包装备或材料合成的成品、产量和消耗。',
  prop_recipes: '配置使用道具仓库材料合成的成品、产量和消耗。',
  stacks: '定义战斗中使用的层数、上限、跨场保留及世界 BOSS 免疫规则。',
}
export const fetchRecords = (category: Category, draft: boolean) =>
  request<RuleRecords>(`/api/v1/catalog/manage/${category}?draft=${draft}`)
export const fetchManageMeta = (draft: boolean) => request<ManageMeta>(`/api/v1/catalog/manage/meta?draft=${draft}`)
const body = (data: unknown) => ({ body: JSON.stringify(data) })
export const saveRecord = (category: Category, key: string | null, version_id: number, before_hash: string | null, data: RuleDocument) =>
  request<RuleRecord>(`/api/v1/edit/manage/${category}${key === null ? '' : `/${encodeURIComponent(key)}`}`,
    { method: key === null ? 'POST' : 'PUT', ...body({ version_id, before_hash, data }) })
export const checkRecord = (category: Category, key: string | null, version_id: number, before_hash: string | null, data: RuleDocument) =>
  request<RuleCheck>(`/api/v1/edit/manage/${category}/check${key === null ? '' : `?key=${encodeURIComponent(key)}`}`,
    { method: 'POST', ...body({ version_id, before_hash, data }) })
export const deleteRecord = (category: Category, record: RuleRecord, version_id: number) =>
  request<null>(`/api/v1/edit/manage/${category}/${encodeURIComponent(record.key)}`,
    { method: 'DELETE', ...body({ version_id, before_hash: record.hash }) })

export function emptyDocument(category: Category, meta: ManageMeta): RuleDocument {
  const id = meta.next_ids[category] ?? 1
  switch (category) {
    case 'effects': return { id: '', name: '', desc: '', params: {}, static: [], auras: [], triggers: [] }
    case 'sets': return { name: '', tiers: [{ pieces: 2, effects: [] }] }
    case 'monsters': return { id: '', name: '', kind: 'normal', level: 1, no: null, stats: { hp: 100, atk: 10 }, coins: 0, exp: 0, rewards: [], prop_rewards: [], info_rewards: [], effects: [] }
    case 'dungeons': return { id, name: '', stamina: 5, hidden_id: '', hidden_rate: 10, encounters: [] }
    case 'drops': return { rewards: [], prop_rewards: [], info_rewards: [] }
    case 'props': return { id, name: '', category: '道具', effect: 'material', amount: 0, blurb: '', dungeon: '', value: 0 }
    case 'recipes': case 'prop_recipes': return { id, output: '', quantity: 1, inputs: [] }
    case 'stacks': return { key: '', name: '', owner: 'foe', max: null, max_stat: null, carry: false, boss_immune: true }
  }
}
