<script setup lang="ts">
import { computed } from 'vue'
import { STATUS_LABELS, type ServiceStatus } from '@/api/system'
import { useSystemStore } from '@/stores/system'

const system = useSystemStore()
const running = computed(() => system.services.filter((s) => s.status === 'running' || s.status === 'external').length)
const attention = computed(() => system.services.length - running.value)
const databases = computed(() => Object.entries(system.health?.logic?.extra?.databases ?? {}))
const databaseNames: Record<string, string> = { rules: '规则库', game: '游戏存档', stats: '统计库', api: '网站账号' }
const tagType = (status: ServiceStatus) =>
  status === 'running' || status === 'external' ? 'success' : status === 'starting' || status === 'restarting' ? 'warning' : 'danger'
</script>

<template>
  <div class="section-title"><h2>系统运行状态</h2><span>服务探测与数据库健康</span></div>
  <el-alert v-if="system.error" :title="system.error" type="error" show-icon :closable="false" class="status-error" />
  <div class="status-metrics" v-loading="system.loading && !system.health && !system.services.length">
    <el-card shadow="never"><span>已探测服务</span><strong>{{ system.services.length || '—' }}</strong></el-card>
    <el-card shadow="never"><span>运行正常</span><strong>{{ system.services.length ? running : '—' }}</strong></el-card>
    <el-card shadow="never" :class="{ warning: attention > 0 }"><span>需要关注</span><strong>{{ system.services.length ? attention : '—' }}</strong></el-card>
    <el-card shadow="never"><span>生效规则版本</span><strong>{{ system.health?.logic?.rules_version ?? '—' }}</strong></el-card>
  </div>
  <el-card shadow="never" class="service-card">
    <el-table v-if="system.services.length" :data="system.services" stripe>
      <el-table-column prop="name" label="服务" min-width="135" />
      <el-table-column label="状态" width="115"><template #default="{ row }"><el-tag :type="tagType(row.status)">{{ STATUS_LABELS[row.status as ServiceStatus] }}</el-tag></template></el-table-column>
      <el-table-column prop="message" label="运行情况" min-width="240" />
    </el-table>
    <el-empty v-else :image-size="60" description="暂未获取到服务状态，请稍后刷新" />
    <div class="databases">
      <b>数据库</b>
      <template v-if="databases.length">
        <el-tag v-for="[name, ok] in databases" :key="name" :type="ok ? 'success' : 'danger'" effect="plain">{{ databaseNames[name] ?? name }} · {{ ok ? '正常' : '异常' }}</el-tag>
      </template>
      <span v-else class="muted">{{ system.health?.logic ? '暂无数据库健康信息' : '逻辑后端暂未返回健康信息' }}</span>
    </div>
  </el-card>
</template>

<style scoped>
.section-title { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; margin-bottom: 16px; }
h2 { font-size: 19px; margin: 0; }
.section-title span, .muted, .status-metrics span { font-size: 13px; color: var(--el-text-color-secondary); }
.status-error { margin-bottom: 16px; }
.status-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.status-metrics strong { display: block; font-size: 28px; margin-top: 8px; }
.warning strong { color: var(--el-color-warning); }
.service-card { margin-top: 12px; }
.databases { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; padding-top: 18px; font-size: 13px; }
.databases b { margin-right: 4px; }
@media (max-width: 760px) { .status-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
