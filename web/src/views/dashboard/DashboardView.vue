<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useSystemStore } from '@/stores/system'
import ServiceStatusPanel from './ServiceStatusPanel.vue'
import GameStatistics from './GameStatistics.vue'

const route = useRoute()
const system = useSystemStore()
const statistics = ref<InstanceType<typeof GameStatistics>>()
const autoRefresh = ref(true)
const refreshing = ref(false)
const refreshedAt = ref('')
const busy = computed(() => refreshing.value || system.loading || statistics.value?.loading)
let timer: ReturnType<typeof setInterval> | undefined

async function refresh() {
  if (refreshing.value || statistics.value?.loading) return
  refreshing.value = true
  try {
    await Promise.all([system.refresh(), statistics.value?.refresh()])
    refreshedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } finally {
    refreshing.value = false
  }
}

async function scrollToSection() {
  await nextTick()
  const id = route.hash.slice(1)
  if (id === 'statistics' || id === 'system') document.getElementById(id)?.scrollIntoView({ block: 'start' })
}
watch(() => route.hash, scrollToSection)
onMounted(() => {
  void refresh()
  void scrollToSection()
  timer = setInterval(() => {
    if (autoRefresh.value && document.visibilityState === 'visible' && !busy.value) void refresh()
  }, 30_000)
})
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <div class="overview-page">
    <div class="page-heading">
      <div><h1>运行概览</h1><p>集中查看服务健康、玩家活跃与游戏各项流水。</p></div>
      <div class="refresh-controls">
        <span class="updated" aria-live="polite">{{ refreshedAt ? `最近刷新 ${refreshedAt}` : '正在读取状态' }}</span>
        <el-switch v-model="autoRefresh" active-text="每 30 秒刷新" />
        <el-button type="primary" :loading="busy" @click="refresh">刷新全部</el-button>
      </div>
    </div>
    <section id="system" aria-label="系统运行状态"><ServiceStatusPanel /></section>
    <section id="statistics" aria-label="游戏统计与流水"><GameStatistics ref="statistics" /></section>
  </div>
</template>

<style scoped>
.overview-page { max-width: 1500px; margin: 0 auto; padding-bottom: 24px; }
.page-heading, .refresh-controls { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
h1 { margin: 0; font-size: 25px; }
.page-heading p, .updated { color: var(--el-text-color-secondary); font-size: 13px; }
.page-heading p { margin: 10px 0 0; }
.page-heading { margin-bottom: 24px; }
section { scroll-margin-top: 16px; }
#statistics { margin-top: 32px; }
@media (max-width: 760px) { .refresh-controls { gap: 10px; } .updated { width: 100%; } }
</style>
