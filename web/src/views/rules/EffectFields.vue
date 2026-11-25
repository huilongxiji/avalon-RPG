<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { ManageMeta, RuleDocument } from '@/api/rulesManage'
import ActionList from './ActionList.vue'
const form = defineModel<RuleDocument>({ required: true })
defineProps<{ meta: ManageMeta; creating: boolean }>()
const paramName = ref('')
function addParam() {
  const key = paramName.value.trim()
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key) || Object.prototype.hasOwnProperty.call(form.value.params, key)) { ElMessage.warning('参数名须为字母、数字和下划线，不能以数字开头或重复'); return }
  form.value.params[key] = 0; paramName.value = ''
}
function optional(obj: RuleDocument, key: string, value: unknown) { if (value === '' || value == null) delete obj[key]; else obj[key] = value }
</script>
<template>
  <div class="grid"><el-form-item label="效果代号（英文、数字、下划线或连字符）" required><el-input v-model="form.id" :disabled="!creating" :maxlength="64" /></el-form-item><el-form-item label="中文名称" required><el-input v-model="form.name" :maxlength="64" /></el-form-item></div>
  <el-form-item label="效果描述（可用 {参数名} 引用下方数值）"><el-input v-model="form.desc" type="textarea" :rows="2" /></el-form-item>
  <h3>数值参数</h3><div v-for="(value, key) in form.params" :key="key" class="inline"><span>{{ key }}</span><el-input-number :model-value="value" @update:model-value="(v: any) => form.params[key] = v" :controls="false" /><el-button link type="danger" @click="delete form.params[key]">移除</el-button></div><div class="inline"><el-input v-model="paramName" placeholder="新参数名，如 bonus" style="max-width: 260px" @keydown.enter.prevent="addParam" /><el-button @click="addParam">添加参数</el-button></div>
  <h3>静态加成 <small>穿上后生效</small></h3>
  <div v-for="(mod, i) in form.static" :key="i" class="block">
    <div class="grid"><el-form-item label="属性"><el-select v-model="mod.stat" filterable><el-option v-for="s in meta.stats" :key="s.key" :value="s.key" :label="s.name" /></el-select></el-form-item><el-form-item label="加成方式"><el-select v-model="mod.op"><el-option v-for="(label, key) in meta.static_ops" :key="key" :value="key" :label="label" /></el-select></el-form-item><el-form-item label="数值 / 表达式"><el-input :model-value="String(mod.value ?? '')" @update:model-value="(v: any) => mod.value = v" placeholder="10 或 bonus" /></el-form-item><el-form-item label="条件（可不填）"><el-input :model-value="mod.if" @update:model-value="(v: any) => optional(mod, 'if', v)" placeholder="如 weapon.magic" /></el-form-item><el-form-item v-if="mod.op === 'max'" label="合并组（可不填）"><el-input v-model="mod.group" /></el-form-item></div><el-button type="danger" link @click="form.static.splice(i, 1)">删除此加成</el-button>
  </div><el-button @click="form.static.push({ stat: 'atk', op: 'add', value: 10 })">添加静态加成</el-button>
  <h3>持续效果 <small>随战斗状态实时计算</small></h3>
  <div v-for="(aura, i) in form.auras" :key="i" class="block"><div class="grid"><el-form-item label="对象"><el-select v-model="aura.target"><el-option value="self" label="自己" /><el-option value="foe" label="对手" /></el-select></el-form-item><el-form-item label="属性"><el-select v-model="aura.stat" filterable><el-option v-for="s in meta.stats" :key="s.key" :value="s.key" :label="s.name" /></el-select></el-form-item><el-form-item label="加成方式"><el-select v-model="aura.op"><el-option v-for="(label, key) in meta.battle_ops" :key="key" :value="key" :label="label" /></el-select></el-form-item><el-form-item label="数值 / 表达式"><el-input :model-value="String(aura.value ?? '')" @update:model-value="(v: any) => aura.value = v" /></el-form-item><el-form-item label="条件（可不填）"><el-input :model-value="aura.if" @update:model-value="(v: any) => optional(aura, 'if', v)" /></el-form-item></div><el-button type="danger" link @click="form.auras.splice(i, 1)">删除此持续效果</el-button></div><el-button @click="form.auras.push({ target: 'self', stat: 'atk', op: 'add', value: 10 })">添加持续效果</el-button>
  <h3>触发逻辑 <small>按优先级与列表顺序执行</small></h3>
  <div v-for="(trigger, i) in form.triggers" :key="i" class="block"><div class="block-title"><b>触发 {{ i + 1 }}</b><div><el-button link :disabled="i === 0" @click="form.triggers.splice(i - 1, 0, form.triggers.splice(i, 1)[0])">上移</el-button><el-button link type="danger" @click="form.triggers.splice(i, 1)">删除触发</el-button></div></div>
    <div class="grid"><el-form-item label="时机" required><el-select v-model="trigger.on" filterable><el-option v-for="(label, key) in meta.triggers" :key="key" :value="key" :label="label" /></el-select></el-form-item><el-form-item label="条件（可不填）"><el-input :model-value="trigger.if" @update:model-value="(v: any) => optional(trigger, 'if', v)" placeholder="如 round_no == 2" /></el-form-item><el-form-item label="概率百分数 / 表达式（留空为必定）"><el-input :model-value="String(trigger.chance ?? '')" @update:model-value="(v: any) => optional(trigger, 'chance', v)" /></el-form-item><el-form-item label="次数限制"><el-select :model-value="trigger.once ?? ''" placeholder="不限制" @update:model-value="(v: any) => optional(trigger, 'once', v)"><el-option value="" label="不限制" /><el-option value="battle" label="每场一次" /><el-option value="run" label="每次挑战一次" /></el-select></el-form-item><el-form-item label="冷却回合"><el-input-number v-model="trigger.cooldown" :min="0" :precision="0" /></el-form-item><el-form-item label="执行优先级（越小越先）"><el-input-number v-model="trigger.priority" :precision="0" /></el-form-item><el-form-item v-if="trigger.on === 'stack_full' || trigger.on === 'stack_gain'" label="仅监听指定层数（可不选）"><el-select :model-value="trigger.stack" clearable @update:model-value="(v: any) => optional(trigger, 'stack', v)"><el-option v-for="s in meta.stacks" :key="s.key" :value="s.key" :label="s.name" /></el-select></el-form-item></div>
    <ActionList v-model="trigger.do" :meta="meta" />
  </div><el-button @click="form.triggers.push({ on: 'round_start', cooldown: 0, priority: 100, do: [{ action: 'heal', target: 'self', value: 10 }] })">添加触发逻辑</el-button>
  <p class="hint">表达式可使用参数名、self.atk、foe.hp_now、round_no、self.stacks.层数代号等。静态加成使用 self.base.atk 等基础属性、self.level、weapon.magic 和 pieces；保存前会检查完整引用和表达式。</p>
</template>
<style scoped>
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 18px; }.inline { display: flex; align-items: center; gap: 12px; margin: 10px 0; }.inline > span { width: 150px; }.block { padding: 16px; margin: 12px 0; background: var(--el-fill-color-light); border-radius: 8px; }.block-title { display: flex; justify-content: space-between; margin-bottom: 15px; }h3 { margin-top: 26px; font-size: 16px; }small, .hint { color: var(--el-text-color-secondary); font-size: 12px; font-weight: normal; }.hint { line-height: 1.8; }
@media(max-width: 600px) { .grid { grid-template-columns: 1fr; } }
</style>
