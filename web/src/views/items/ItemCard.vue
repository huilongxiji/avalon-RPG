<script setup lang="ts">
// 一张装备卡片：名称、编号、部位、伤害类型；主属性大号数字；其他属性最多 3 个；套装标签；效果摘要
import { computed } from 'vue'
import { formatStat, type ItemCard } from '@/api/catalog'

const props = defineProps<{ item: ItemCard }>()
const emit = defineEmits<{ open: [id: number]; 'jump-set': [name: string] }>()

const extraShown = computed(() => props.item.extra_stats.slice(0, 3))
const extraMore = computed(() => props.item.extra_stats.length - extraShown.value.length)
const secondary = computed(() => props.item.sets.filter((s) => s.role === 'secondary'))

const DAMAGE_TAG: Record<string, 'danger' | 'primary' | 'warning'> = {
  physical: 'danger',
  magic: 'primary',
  precision: 'warning',
}
</script>

<template>
  <el-card class="card" :class="{ retired: item.retired }" shadow="hover" :body-style="{ padding: '12px' }" @click="emit('open', item.id)">
    <div class="head">
      <span class="name" :title="item.name">{{ item.name }}</span>
      <span class="id">#{{ item.id }}</span>
    </div>
    <div class="tags">
      <el-tag size="small" type="info">{{ item.slot_label }}</el-tag>
      <el-tag v-if="item.damage_label" size="small" :type="DAMAGE_TAG[item.damage_type ?? ''] ?? 'info'">
        {{ item.damage_label }}
      </el-tag>
      <el-tag v-if="item.price" size="small" type="info" effect="plain">价格 {{ item.price }}</el-tag>
      <el-tag v-if="item.added" size="small" type="success" effect="dark">新建</el-tag>
      <el-tag v-else-if="item.changed" size="small" type="warning" effect="dark">已修改</el-tag>
      <el-tag v-if="item.retired" size="small" type="danger" effect="plain">已下架</el-tag>
    </div>

    <div v-if="item.main_stats.length" class="main-stats">
      <div v-for="s in item.main_stats" :key="s.key" class="stat">
        <div class="value" :class="{ negative: s.value < 0 }">{{ formatStat(s) }}</div>
        <div class="label">{{ s.name }}</div>
      </div>
    </div>
    <div v-else class="no-stats">没有基础属性</div>

    <div v-if="item.extra_stats.length" class="extra">
      <el-tag v-for="s in extraShown" :key="s.key" size="small" effect="plain">
        {{ s.name }} {{ formatStat(s) }}
      </el-tag>
      <el-tooltip v-if="extraMore > 0" placement="top">
        <template #content>
          <div v-for="s in item.extra_stats.slice(3)" :key="s.key">{{ s.name }} {{ formatStat(s) }}</div>
        </template>
        <el-tag size="small" effect="plain" type="info">+{{ extraMore }}</el-tag>
      </el-tooltip>
    </div>

    <div v-if="secondary.length" class="sets">
      <el-tag
        v-for="s in secondary"
        :key="s.name"
        size="small"
        type="success"
        class="link"
        @click.stop="emit('jump-set', s.name)"
      >
        副：{{ s.name }}
      </el-tag>
    </div>

    <el-tooltip v-if="item.effect_brief" placement="bottom" :show-after="300">
      <template #content>
        <div class="tip">{{ item.effect_brief }}</div>
      </template>
      <div class="brief">{{ item.effect_brief }}</div>
    </el-tooltip>
  </el-card>
</template>

<style scoped>
.card {
  cursor: pointer;
  height: 100%;
}
.card.retired {
  opacity: 0.6;
}
.head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.name {
  font-weight: 600;
  font-size: 15px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.id {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  flex-shrink: 0;
}
.tags,
.extra,
.sets {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}
.main-stats {
  display: flex;
  gap: 12px;
  margin-top: 10px;
}
.stat .value {
  font-size: 20px;
  font-weight: 600;
  line-height: 1.1;
}
.stat .value.negative {
  color: var(--el-color-danger);
}
.stat .label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.no-stats {
  margin-top: 10px;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
.link {
  cursor: pointer;
}
.brief {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.tip {
  max-width: 360px;
  line-height: 1.6;
}
</style>
