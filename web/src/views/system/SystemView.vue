<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { STATUS_LABELS, type ServiceStatus } from '@/api/system'
import { useSystemStore } from '@/stores/system'

const system = useSystemStore()
onMounted(() => system.refresh())

const tagType = (s: ServiceStatus) =>
  s === 'running' || s === 'external' ? 'success' : s === 'starting' || s === 'restarting' ? 'warning' : 'danger'

const databases = computed(() => Object.entries(system.health?.logic?.extra?.databases ?? {}))
</script>

<template>
  <div>
    <el-alert v-if="system.error" :title="system.error" type="error" show-icon :closable="false" />
    <el-card style="margin-top: 12px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>各服务运行状态</span>
          <el-button :loading="system.loading" @click="system.refresh()">刷新</el-button>
        </div>
      </template>
      <el-empty
        v-if="!system.services.length"
        description="没有收到编排程序的状态（用 uv run avalon-ctl up 启动后这里会显示各服务）"
      />
      <el-table v-else :data="system.services">
        <el-table-column prop="name" label="服务" />
        <el-table-column label="状态">
          <template #default="{ row }">
            <el-tag :type="tagType(row.status)">{{ STATUS_LABELS[row.status as ServiceStatus] }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="pid" label="进程" />
        <el-table-column prop="restarts" label="重启次数" />
        <el-table-column prop="message" label="说明" />
      </el-table>
    </el-card>
    <el-card header="数据库" style="margin-top: 12px">
      <el-descriptions :column="4" border>
        <el-descriptions-item v-for="[name, ok] in databases" :key="name" :label="name">
          <el-tag :type="ok ? 'success' : 'danger'">{{ ok ? '正常' : '异常' }}</el-tag>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>
  </div>
</template>
