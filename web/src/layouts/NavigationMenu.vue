<script setup lang="ts">
defineProps<{ activeMenu: string; canManageUsers: boolean }>()
const emit = defineEmits<{ select: [] }>()
</script>

<template>
  <el-menu class="navigation-menu" router :default-active="activeMenu" @select="emit('select')">
    <el-menu-item index="/dashboard">运行概览</el-menu-item>
    <el-menu-item index="/settings">年卡设定</el-menu-item>
    <el-menu-item index="/items">装备与套装</el-menu-item>
    <el-menu-item index="/formulas">公式</el-menu-item>
    <el-menu-item v-if="canManageUsers" index="/users">网站用户</el-menu-item>
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
  </el-menu>
</template>

<style scoped>
.navigation-menu { border-right: 0; }
</style>
