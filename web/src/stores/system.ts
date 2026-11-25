import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchHealth, fetchServices, type ServiceState, type SystemHealth } from '@/api/system'
import { RequestError } from '@/api/client'

export const useSystemStore = defineStore('system', () => {
  const services = ref<ServiceState[]>([])
  const health = ref<SystemHealth | null>(null)
  const error = ref('')
  const loading = ref(false)

  async function refresh() {
    loading.value = true
    error.value = ''
    try {
      const [h, s] = await Promise.all([fetchHealth(), fetchServices()])
      health.value = h
      services.value = s ?? []
    } catch (e) {
      error.value = e instanceof RequestError ? e.message : '刷新失败'
      health.value = null
    } finally {
      loading.value = false
    }
  }

  return { services, health, error, loading, refresh }
})
