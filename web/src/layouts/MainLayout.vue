<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useSystemStore } from '@/stores/system'
import { useAuthStore } from '@/stores/auth'
import { ROLE_LABELS } from '@/api/accounts'
import { showError } from '@/api/edit'
import PasswordDialog from '@/components/PasswordDialog.vue'
import NavigationMenu from './NavigationMenu.vue'

const route = useRoute()
const system = useSystemStore()
const auth = useAuthStore()
const passwordOpen = ref(false)
const loggingOut = ref(false)
const mobileMenuOpen = ref(false)
let mobileQuery: MediaQueryList | undefined
async function signOut() {
  loggingOut.value = true
  try { await auth.signOut() } catch (e) { await showError(e, '退出失败') }
  finally { loggingOut.value = false }
}
function accountAction(command: string) {
  if (command === 'password') passwordOpen.value = true
  if (command === 'logout') void signOut()
}
function closeDesktopDrawer() {
  if (!mobileQuery?.matches) mobileMenuOpen.value = false
}
const title = computed(() => (route.meta.title as string) ?? '')
// 装备详情（/items/编号）也高亮“装备与套装”。
const activeMenu = computed(() => (route.path.startsWith('/items') ? '/items' : route.path))
const rulesVersion = computed(() => system.health?.logic?.rules_version)

watch(() => route.fullPath, () => { mobileMenuOpen.value = false })
onMounted(() => {
  void system.refresh()
  mobileQuery = window.matchMedia('(max-width: 640px)')
  mobileQuery.addEventListener('change', closeDesktopDrawer)
})
onBeforeUnmount(() => mobileQuery?.removeEventListener('change', closeDesktopDrawer))
</script>

<template>
  <el-container class="layout">
    <el-aside width="200px" class="aside">
      <div class="logo">阿瓦隆管理后台</div>
      <NavigationMenu :active-menu="activeMenu" :can-manage-users="auth.canManageUsers" />
    </el-aside>
    <el-container class="content">
      <el-header class="header">
        <div class="heading">
          <el-button class="mobile-menu-button" size="small" aria-label="打开导航菜单" aria-controls="mobile-navigation" :aria-expanded="mobileMenuOpen" @click="mobileMenuOpen = true">菜单</el-button>
          <span class="title">{{ title }}</span>
        </div>
        <div class="meta">
          <el-tag v-if="system.error" class="rule-tag" type="danger">{{ system.error }}</el-tag>
          <el-tag v-else class="rule-tag" type="info">
            规则版本：{{ system.health?.logic ? rulesVersion ?? '尚未发布' : '暂不可用' }}
          </el-tag>
          <span v-if="auth.user" class="desktop-account">{{ auth.user.username }} · {{ ROLE_LABELS[auth.user.role] }}</span>
          <div class="desktop-actions">
            <el-button text @click="passwordOpen = true">修改密码</el-button>
            <el-button text :loading="loggingOut" @click="signOut">退出登录</el-button>
          </div>
          <el-dropdown class="mobile-account" trigger="click" placement="bottom-end" @command="accountAction">
            <el-button size="small" :loading="loggingOut" aria-label="账户操作"><span class="account-name">{{ auth.user?.username ?? '账户' }}</span></el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-if="auth.user" disabled>{{ ROLE_LABELS[auth.user.role] }}</el-dropdown-item>
                <el-dropdown-item command="password">修改密码</el-dropdown-item>
                <el-dropdown-item command="logout" :disabled="loggingOut">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
  <el-drawer id="mobile-navigation" v-model="mobileMenuOpen" class="mobile-navigation" title="阿瓦隆管理后台" direction="ltr" size="min(280px, 86vw)" append-to-body>
    <NavigationMenu :active-menu="activeMenu" :can-manage-users="auth.canManageUsers" @select="mobileMenuOpen = false" />
  </el-drawer>
  <PasswordDialog v-model="passwordOpen" />
</template>

<style scoped>
.layout { height: 100%; }
.aside { border-right: 1px solid var(--el-border-color); }
.content { min-width: 0; }
.logo { padding: 16px; font-weight: 600; font-size: 16px; }
.header { display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--el-border-color); min-height: 60px; height: auto; padding-block: 10px; gap: 12px; }
.heading { display: flex; align-items: center; gap: 12px; min-width: 0; }
.title { font-size: 18px; font-weight: 600; }
.meta { display: flex; align-items: center; gap: 10px; font-size: 13px; flex-wrap: wrap; min-width: 0; }
.desktop-actions { display: flex; align-items: center; }
.rule-tag { max-width: 100%; height: auto; min-height: 24px; white-space: normal; line-height: 1.5; padding-block: 2px; }
.mobile-menu-button, .mobile-account { display: none; }
.mobile-navigation :deep(.el-drawer__body) { padding: 0; }
@media (min-width: 641px) and (max-width: 760px) {
  .aside { width: 160px !important; }
  .header { align-items: flex-start; flex-direction: column; }
}
@media (max-width: 640px) {
  .aside { display: none; }
  .header { padding: 10px 12px; align-items: stretch; flex-direction: column; gap: 8px; }
  .heading { gap: 10px; }
  .title { font-size: 17px; }
  .mobile-menu-button { display: inline-flex; }
  .desktop-account, .desktop-actions { display: none; }
  .meta { flex-wrap: nowrap; justify-content: space-between; gap: 8px; }
  .rule-tag { min-width: 0; }
  .mobile-account { display: inline-flex; flex-shrink: 0; }
  .account-name { display: block; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .main { padding: 16px 12px; }
}
</style>
