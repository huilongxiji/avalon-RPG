import { createRouter, createWebHistory } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('@/views/auth/LoginView.vue'), meta: { title: '登录', public: true } },
    {
      path: '/',
      component: MainLayout,
      children: [
        { path: 'effects', component: () => import('@/views/rules/RulesManageView.vue'), props: { category: 'effects' }, meta: { title: '效果管理' } },
        { path: 'sets', component: () => import('@/views/rules/RulesManageView.vue'), props: { category: 'sets' }, meta: { title: '套装管理' } },
        { path: 'monsters', component: () => import('@/views/rules/RulesManageView.vue'), props: { category: 'monsters' }, meta: { title: '怪物管理' } },
        { path: 'dungeons', component: () => import('@/views/rules/RulesManageView.vue'), props: { category: 'dungeons' }, meta: { title: '副本管理' } },
        { path: 'drops', component: () => import('@/views/rules/RulesManageView.vue'), props: { category: 'drops' }, meta: { title: '掉落管理' } },
        { path: 'props', component: () => import('@/views/rules/RulesManageView.vue'), props: { category: 'props' }, meta: { title: '道具管理' } },
        { path: 'recipes', component: () => import('@/views/rules/RulesManageView.vue'), props: { category: 'recipes' }, meta: { title: '装备配方' } },
        { path: 'prop-recipes', component: () => import('@/views/rules/RulesManageView.vue'), props: { category: 'prop_recipes' }, meta: { title: '道具配方' } },
        { path: 'stacks', component: () => import('@/views/rules/RulesManageView.vue'), props: { category: 'stacks' }, meta: { title: '层数管理' } },
        { path: 'users', component: () => import('@/views/users/UsersView.vue'), meta: { title: '网站用户', superOnly: true } },
        { path: 'stats', component: () => import('@/views/stats/StatsView.vue'), meta: { title: '统计流水' } },
        { path: 'settings', component: () => import('@/views/settings/SettingsView.vue'), meta: { title: '年卡设定' } },
        { path: '', redirect: '/dashboard' },
        {
          path: 'dashboard',
          component: () => import('@/views/dashboard/DashboardView.vue'),
          meta: { title: '数据大屏' },
        },
        {
          path: 'items/:id?',
          component: () => import('@/views/items/ItemsView.vue'),
          meta: { title: '装备与套装' },
        },
        {
          path: 'formulas',
          component: () => import('@/views/formulas/FormulasView.vue'),
          meta: { title: '公式' },
        },
        {
          path: 'system',
          component: () => import('@/views/system/SystemView.vue'),
          meta: { title: '系统状态' },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.restore()
  if (!to.meta.public && !auth.user) return { path: '/login', query: { redirect: to.fullPath } }
  if (to.meta.public && auth.user) return '/dashboard'
  if (to.meta.superOnly && !auth.canManageUsers) return '/dashboard'
})
router.afterEach((to) => { document.title = `${to.meta.title ?? '管理后台'} · 阿瓦隆` })

export default router
