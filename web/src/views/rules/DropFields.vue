<script setup lang="ts">
import type { ManageMeta, RuleDocument } from '@/api/rulesManage'
const form = defineModel<RuleDocument>({ required: true })
defineProps<{ meta: ManageMeta }>()
const groups = [{ key: 'rewards', label: '装备掉落', source: 'items' }, { key: 'prop_rewards', label: '道具掉落', source: 'props' }] as const
</script>
<template>
  <section v-for="group in groups" :key="group.key" class="drop-section">
    <h3>{{ group.label }}</h3>
    <div v-for="(row, i) in form[group.key]" :key="i" class="drop-row">
      <el-select v-model="row.name" filterable placeholder="选择物品" :aria-label="`${group.label}物品 ${i + 1}`"><el-option v-for="item in meta[group.source]" :key="item.key" :value="item.key" :label="item.name" /></el-select>
      <el-input-number v-model="row.chance" :min="0" :max="100" :precision="4" :aria-label="`${group.label}概率 ${i + 1}`" /><span>%</span><el-button type="danger" link @click="form[group.key].splice(i, 1)">移除</el-button>
    </div>
    <el-button @click="form[group.key].push({ name: '', chance: 10 })">添加{{ group.label }}</el-button>
  </section>
  <el-form-item label="归属装备（不额外产生掉落）"><el-select v-model="form.info_rewards" multiple filterable placeholder="选择归属装备"><el-option v-for="item in meta.items" :key="item.key" :value="item.key" :label="item.name" /></el-select></el-form-item>
  <p class="hint">每项概率独立判断。清空列表表示不再发放这一类掉落；已有物品不受影响。</p>
</template>
<style scoped>
h3 { font-size: 15px; }.drop-section { margin-bottom: 22px; }.drop-row { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }.drop-row .el-select { flex: 1; }.hint { color: var(--el-text-color-secondary); font-size: 13px; }
</style>
