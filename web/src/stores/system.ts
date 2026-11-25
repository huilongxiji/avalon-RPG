import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchHealth, fetchServices, type ServiceState, type SystemHealth } from '@/api/system'
import { RequestError } from '@/api/client'

export const useSystemStore = defineStore('system', () => {
  const services = ref<ServiceState[]>([])
  const health = ref<SystemHealth | null>(null)
  const error = ref('')
  const loading = ref(false)
  let pending: Promise<void> | null = null

  // 布局标题和运行概览共用状态；同一时刻只发起一轮探测。
  function refresh(): Promise<void> {
    if (pending) return pending
    loading.value = true
    error.value = ''
    pending = (async () => {
      try {
        const [h, s] = await Promise.allSettled([fetchHealth(), fetchServices()])
        health.value = h.status === 'fulfilled' ? h.value : null
        services.value = s.status === 'fulfilled' ? s.value ?? [] : []
        const failures = [h, s].flatMap((result) => result.status === 'rejected'
          ? [result.reason instanceof RequestError ? result.reason.message : '状态刷新失败'] : [])
        error.value = [...new Set(failures)].join('；')
      } finally {
        loading.value = false
        pending = null
      }
    })()
    return pending
  }

  return { services, health, error, loading, refresh }
})
