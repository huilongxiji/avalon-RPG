<script setup lang="ts">
// 服务状态大屏；实际玩家收支、战斗、掉落和效果触发见统计流水页。
import { computed, onMounted } from 'vue'
import type { EChartsOption } from 'echarts'
import EChart from '@/components/EChart.vue'
import { STATUS_LABELS } from '@/api/system'
import { useSystemStore } from '@/stores/system'

const system = useSystemStore()
onMounted(() => system.refresh())

const option = computed<EChartsOption>(() => {
  const counts = new Map<string, number>()
  for (const s of system.services) {
    const label = STATUS_LABELS[s.status]
    counts.set(label, (counts.get(label) ?? 0) + 1)
  }
  return {
    title: { text: '服务状态分布', left: 'center' },
    tooltip: { trigger: 'item' },
    series: [
      {
        type: 'pie',
        radius: ['40%', '65%'],
        data: [...counts].map(([name, value]) => ({ name, value })),
      },
    ],
  }
})
</script>

<template>
  <el-row :gutter="12">
    <el-col :span="8">
      <el-card><el-statistic title="服务总数" :value="system.services.length" /></el-card>
    </el-col>
    <el-col :span="8">
      <el-card>
        <el-statistic
          title="运行中"
          :value="system.services.filter((s) => s.status === 'running' || s.status === 'external').length"
        />
      </el-card>
    </el-col>
    <el-col :span="8">
      <el-card>
        <el-statistic title="当前规则版本" :value="system.health?.logic?.rules_version ?? 0" />
      </el-card>
    </el-col>
  </el-row>
  <el-card style="margin-top: 12px">
    <EChart :option="option" height="360px" />
  </el-card>
  <el-card style="margin-top: 12px">
    <p>玩家活跃、资源收支、战斗、掉落与效果触发已接入统计流水。</p>
    <router-link to="/stats"><el-button type="primary">查看统计流水</el-button></router-link>
  </el-card>
</template>
