<script setup lang="ts">
import { computed, ref } from 'vue'
import type { StatInfo } from '@/api/catalog'
const values = defineModel<Record<string, number>>({ required: true })
const props = defineProps<{ stats: StatInfo[] }>()
const choice = ref('')
const available = computed(() => props.stats.filter(s => !(s.key in values.value)))
function add() { if (choice.value) { values.value[choice.value] = 0; choice.value = '' } }
</script>
<template>
  <div class="stat-grid">
    <div v-for="(value, key) in values" :key="key" class="stat-row"><span>{{ stats.find(s => s.key === key)?.name ?? key }}{{ stats.find(s => s.key === key)?.percent ? '（%）' : '' }}</span><el-input-number :model-value="value" :controls="false" @update:model-value="(v: any) => values[key] = v as number" /><el-button link type="danger" @click="delete values[key]">移除</el-button></div>
  </div>
  <div class="add-row"><el-select v-model="choice" filterable placeholder="选择要添加的属性" style="width: 240px"><el-option v-for="stat in available" :key="stat.key" :value="stat.key" :label="stat.name" /></el-select><el-button :disabled="!choice" @click="add">添加属性</el-button></div>
</template>
<style scoped>
.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 10px; }
.stat-row { display: flex; gap: 10px; align-items: center; }.stat-row > span { flex: 1; }.stat-row .el-input-number { width: 130px; }
.add-row { display: flex; gap: 10px; margin-top: 14px; }
</style>
