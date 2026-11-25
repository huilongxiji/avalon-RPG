import { defineStore } from 'pinia'
import { fetchIdentity, login, logout, type Identity, type WebUser } from '@/api/accounts'
import { RequestError, setCsrfToken } from '@/api/client'

let pending: Promise<void> | null = null
export const useAuthStore = defineStore('auth', {
  state: () => ({ user: null as WebUser | null, checked: false, error: '' }),
  getters: { canManageUsers: (s) => s.user?.role === 'super' },
  actions: {
    accept(identity: Identity) {
      this.user = identity.user
      this.checked = true
      this.error = ''
      setCsrfToken(identity.csrf_token)
    },
    clear() {
      this.user = null
      this.checked = true
      setCsrfToken('')
    },
    async restore() {
      if (this.checked) return
      if (pending) return pending
      pending = (async () => {
        try { this.accept(await fetchIdentity()) }
        catch (e) {
          this.clear()
          if (!(e instanceof RequestError && e.code === 'unauthorized')) this.error = (e as Error).message
        }
      })()
      try { await pending } finally { pending = null }
    },
    async signIn(username: string, password: string) { this.accept(await login(username, password)) },
    async signOut() {
      await logout()
      this.clear()
      // 清空所有页面缓存，避免下一位使用者看到前一会话的状态。
      window.location.replace('/login')
    },
  },
})
