<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useSystemStore } from '@/stores/system'
import { useAuthStore } from '@/stores/auth'
import { ROLE_LABELS } from '@/api/accounts'
import { showError } from '@/api/edit'
import PasswordDialog from '@/components/PasswordDialog.vue'

const route = useRoute()
const system = useSystemStore()
const auth = useAuthStore()
const passwordOpen = ref(false)
const loggingOut = ref(false)
async function signOut() {
  loggingOut.value = true
  try { await auth.signOut() } catch (e) { await showError(e, '退出失败') }
  finally { loggingOut.value = false }
}
const title = computed(() => (route.meta.title as string) ?? '')
// 装备详情（/items/编号）也高亮"装备与套装"
const activeMenu = computed(() => (route.path.startsWith('/items') ? '/items' : route.path))
const rulesVersion = computed(() => system.health?.logic?.rules_version)

onMounted(() => system.refresh())
</script>

<template>
  <el-container class="layout">
    <el-aside width="200px" class="aside">
      <div class="logo">阿瓦隆管理后台</div>
      <el-menu router :default-active="activeMenu">
        <el-menu-item index="/dashboard">数据大屏</el-menu-item>
        <el-menu-item index="/stats">统计流水</el-menu-item>
        <el-menu-item index="/settings">年卡设定</el-menu-item>
        <el-menu-item index="/items">装备与套装</el-menu-item>
        <el-menu-item index="/formulas">公式</el-menu-item>
        <el-menu-item index="/system">系统状态</el-menu-item>
        <el-menu-item v-if="auth.canManageUsers" index="/users">网站用户</el-menu-item>
        <el-sub-menu index="rules"><template #title>其他规则管理</template>
          <el-menu-item index="/effects">效果管理</el-menu-item>
          <el-menu-item index="/sets">套装管理</el-menu-item>
          <el-menu-item index="/stacks">层数管理</el-menu-item>
          <el-menu-item index="/monsters">怪物管理</el-menu-item>
          <el-menu-item index="/dungeons">副本管理</el-menu-item>
          <el-menu-item index="/drops">掉落管理</el-menu-item>
          <el-menu-item index="/props">道具管理</el-menu-item>
          <el-menu-item index="/recipes">装备配方</el-menu-item>
          <el-menu-item index="/prop-recipes">道具配方</el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/excel" disabled title="Excel 导出与实时连接（后续开放）">Excel 连接（后续开放）</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span class="title">{{ title }}</span>
        <span class="meta">
          <el-tag v-if="system.error" type="danger">{{ system.error }}</el-tag>
          <el-tag v-else type="info">
            规则版本：{{ rulesVersion ?? '尚未导入' }}
          </el-tag>
          <span v-if="auth.user">{{ auth.user.username }} · {{ ROLE_LABELS[auth.user.role] }}</span>
          <el-button text @click="passwordOpen = true">修改密码</el-button>
          <el-button text :loading="loggingOut" @click="signOut">退出登录</el-button>
        </span>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
  <PasswordDialog v-model="passwordOpen" />
</template>

<style scoped>
.layout {
  height: 100%;
}
.aside {
  border-right: 1px solid var(--el-border-color);
}
.logo {
  padding: 16px;
  font-weight: 600;
  font-size: 16px;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--el-border-color);
}
.title {
  font-size: 18px;
  font-weight: 600;
}
.meta { display: flex; align-items: center; gap: 10px; font-size: 13px; flex-wrap: wrap; }
.header { min-height: 60px; height: auto; padding-block: 10px; gap: 12px; }
@media (max-width: 760px) { .aside { width: 160px !important; } .header { align-items: flex-start; flex-direction: column; } }
</style>
