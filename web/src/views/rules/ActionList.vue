<script setup lang="ts">
import type { ManageMeta, RuleDocument } from '@/api/rulesManage'
const actions = defineModel<RuleDocument[]>({ required: true })
const props = defineProps<{ meta: ManageMeta }>()
type Field = { key: string; label: string; type?: 'choice' | 'bool' | 'text' | 'effects'; optional?: boolean }
const target: Field = { key: 'target', label: '对象', type: 'choice' }
const value: Field = { key: 'value', label: '数值 / 表达式' }
const templates: Record<string, RuleDocument> = {
  modify_stat: { target: 'self', scope: 'battle', stat: 'atk', op: 'add', value: 10 },
  damage: { target: 'foe', kind: 'magic', value: 'self.atk' },
  replace_hit: { hits: [{ kind: 'physical', value: 'self.atk' }] },
  set_hit: { part: 'physical', value: 10 }, scale_hit: { value: 120 }, reduce_hit: { value: 10 },
  chase: { base: 'hit.damage', pct: 90, decay: 10, crit_rate: 'self.crit', crit_dmg: 'self.crit_dmg', counter: 'chase_count' },
  execute: { target: 'foe' }, lose_hp: { value: 10 }, heal: { target: 'self', value: 10 }, shield: { target: 'self', value: 10 },
  stack: { name: '', op: 'add', value: 1 }, prevent: {}, flag: { name: '', value: 1 }, carry: { name: '', value: 1 },
  note: { text: '' }, random: { choices: [{ label: '选项 1', do: [{ action: 'heal', target: 'self', value: 10 }] }] },
}
function change(i: number, kind: string) { actions.value[i] = { action: kind, ...JSON.parse(JSON.stringify(templates[kind] ?? {})) } }
function fields(node: RuleDocument): Field[] {
  switch (node.action) {
    case 'modify_stat': return [target, { key: 'scope', label: '作用范围', type: 'choice' }, { key: 'stat', label: '属性', type: 'choice' }, { key: 'op', label: '修改方式', type: 'choice' }, value, { key: 'rounds', label: '持续回合（可不填）', optional: true }]
    case 'damage': return [target, { key: 'kind', label: '伤害种类', type: 'choice' }, value,
      ...[['ignore_def', '无视防御 %'], ['ignore_resist', '无视法抗 %'], ['crit_rate', '独立暴击率 %'], ['crit_dmg', '独立暴伤 %']].map(([key, label]) => ({ key: key!, label: label! + '（可不填）', optional: true })),
      ...[['pen', '应用穿透'], ['can_crit', '允许暴击'], ['bonus', '应用伤害加成'], ['base_def', '按基础防御计算']].map(([key, label]) => ({ key: key!, label: label!, type: 'bool' as const })),
      { key: 'not_lowered_by', label: '不受指定效果减伤', type: 'effects' }, { key: 'label', label: '战报名称（可不填）', type: 'text', optional: true }]
    case 'set_hit': return [{ key: 'part', label: '伤害部分', type: 'choice' }, value]
    case 'scale_hit': return [value, { key: 'base', label: '比例分母（留空为 100）', optional: true }, { key: 'with_true', label: '同时缩放真实伤害', type: 'bool' }, { key: 'at_least_1', label: '缩放后伤害至少为 1', type: 'bool' }]
    case 'reduce_hit': return [value]
    case 'chase': return [['base', '伤害基数'], ['pct', '初始比例 %'], ['decay', '每次递减 %'], ['crit_rate', '暴击率 %'], ['crit_dmg', '暴击伤害 %']].map(([key, label]) => ({ key: key!, label: label! })).concat([{ key: 'counter', label: '计数标记名', type: 'text' }, { key: 'label', label: '战报名称（可不填）', type: 'text', optional: true }] as Field[])
    case 'execute': return [target, { key: 'label', label: '战报名称（可不填）', type: 'text', optional: true }]
    case 'lose_hp': return [value]
    case 'heal': case 'shield': return [target, value]
    case 'stack': return [{ key: 'name', label: '层数', type: 'choice' }, target, { key: 'op', label: '操作', type: 'choice' }, ...(node.op === 'clear' ? [] : [value])]
    case 'flag': case 'carry': return [{ key: 'name', label: '标记名', type: 'text' }, value, ...(node.action === 'flag' ? [{ key: 'carry', label: '跨场保留', type: 'bool' as const }] : [])]
    case 'note': return [{ key: 'text', label: '战报说明', type: 'text' }]
    default: return []
  }
}
function options(node: RuleDocument, key: string) {
  if (key === 'stat') return props.meta.stats.map(s => ({ key: s.key, name: s.name }))
  if (key === 'name') return props.meta.stacks
  const map = key === 'target' ? { self: '自己', foe: '对手' }
    : key === 'scope' ? { battle: '本场战斗的加成', panel: '直接修改面板' }
    : key === 'kind' || key === 'part' ? { physical: '物理', magic: '法术', true: '真实' }
    : node.action === 'stack' ? { add: '增加', remove: '减少', clear: '清空', set: '设为' }
    : node.scope === 'panel' ? { add: '增加', mul: '乘以', set: '设为' } : props.meta.battle_ops
  return Object.entries(map).map(([key, name]) => ({ key, name: name as string }))
}
function defaultChoice(node: RuleDocument, key: string) {
  if (key === 'scope') return 'battle'
  if (key === 'op') return 'add'
  if (key === 'target') return ['damage', 'execute'].includes(node.action) ? 'foe' : node.action === 'stack' ? '' : 'self'
  return ''
}
function set(node: RuleDocument, field: Field, next: unknown) {
  if (field.optional && (next === '' || next == null)) delete node[field.key]
  else node[field.key] = next
  if (field.key === 'scope') node.op = 'add'
}
</script>

<template>
  <div class="actions">
    <div v-for="(node, i) in actions" :key="i" class="action-block">
      <div class="action-heading"><b>动作 {{ i + 1 }}</b><el-select :model-value="node.action" filterable style="flex: 1" @update:model-value="(kind: string) => change(i, kind)"><el-option v-for="(label, key) in meta.actions" :key="key" :value="key" :label="label" /></el-select><el-button link :disabled="i === 0" @click="actions.splice(i - 1, 0, actions.splice(i, 1)[0]!)">上移</el-button><el-button link type="danger" @click="actions.splice(i, 1)">移除</el-button></div>
      <div class="grid"><el-form-item label="动作条件（可不填）"><el-input :model-value="node.if" @update:model-value="(v: any) => set(node, {key: 'if', label: '', optional: true}, v)" /></el-form-item>
        <el-form-item v-for="field in fields(node)" :key="field.key" :label="field.label">
          <el-select v-if="field.type === 'choice'" :model-value="node[field.key] ?? defaultChoice(node, field.key)" :placeholder="node.action === 'stack' && field.key === 'target' ? '按层数定义' : '请选择'" filterable :clearable="node.action === 'stack' && field.key === 'target'" @update:model-value="(v: any) => set(node, {...field, optional: node.action === 'stack' && field.key === 'target'}, v)"><el-option v-for="option in options(node, field.key)" :key="option.key" :value="option.key" :label="option.name" /></el-select>
          <el-switch v-else-if="field.type === 'bool'" :model-value="!!node[field.key]" @update:model-value="(v: any) => set(node, field, v)" />
          <el-select v-else-if="field.type === 'effects'" v-model="node[field.key]" multiple filterable><el-option v-for="e in meta.effects" :key="e.key" :value="e.key" :label="e.name" /></el-select>
          <el-input v-else :model-value="String(node[field.key] ?? '')" @update:model-value="(v: any) => set(node, field, v)" />
        </el-form-item>
      </div>
      <template v-if="node.action === 'replace_hit'">
        <el-form-item label="分段模式"><el-select :model-value="node.multi == null ? 'auto' : node.multi ? 'multi' : 'single'" @update:model-value="(v: any) => v === 'auto' ? delete node.multi : node.multi = v === 'multi'"><el-option value="auto" label="自动判断" /><el-option value="single" label="单段" /><el-option value="multi" label="多段" /></el-select></el-form-item>
        <div v-for="(hit, j) in node.hits" :key="j" class="inline"><el-select v-model="hit.kind"><el-option value="physical" label="物理" /><el-option value="magic" label="法术" /><el-option value="true" label="真实" /></el-select><el-input :model-value="String(hit.value ?? '')" placeholder="伤害表达式" @update:model-value="(v: any) => hit.value = v" /><el-button link type="danger" @click="node.hits.splice(j, 1)">移除</el-button></div><el-button @click="node.hits.push({ kind: 'physical', value: 'self.atk' })">添加攻击段</el-button>
      </template>
      <template v-if="node.action === 'random'">
        <div v-for="(choice, j) in node.choices" :key="j" class="choice"><div class="inline"><el-input v-model="choice.label" placeholder="选项名称" /><el-input :model-value="String(choice.weight ?? '')" placeholder="权重（全留空为等概率）" @update:model-value="(v: any) => set(choice, {key: 'weight', label: '', optional: true}, v)" /><el-button link type="danger" @click="node.choices.splice(j, 1)">删除选项</el-button></div><ActionList v-model="choice.do" :meta="meta" /></div><el-button @click="node.choices.push({ label: `选项 ${node.choices.length + 1}`, do: [{ action: 'note', text: '触发效果' }] })">添加随机选项</el-button>
      </template>
    </div>
    <el-button @click="actions.push({ action: 'heal', target: 'self', value: 10 })">添加动作</el-button>
  </div>
</template>
<style scoped>
.action-block { padding: 14px; border: 1px solid var(--el-border-color); border-radius: 6px; margin: 12px 0; background: white; }.action-heading, .inline { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 14px; }.choice { border-left: 3px solid var(--el-color-primary-light-7); padding: 10px 0 10px 16px; margin: 12px 0; }
@media(max-width: 600px) { .grid { grid-template-columns: 1fr; }.action-heading { flex-wrap: wrap; } }
</style>
