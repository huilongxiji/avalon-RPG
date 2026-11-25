<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fetchUsers, updateUser, ROLE_HELP, ROLE_LABELS, type Role, type WebUser } from '@/api/accounts'
import { useAuthStore } from '@/stores/auth'
import PasswordDialog from '@/components/PasswordDialog.vue'

const auth = useAuthStore()
const rows = ref<WebUser[]>([])
const total = ref(0)
const page = ref(1)
const q = ref('')
const role = ref<Role | ''>('')
const status = ref('')
const loading = ref(false)
const error = ref('')
const editing = ref<WebUser | null>(null)
const editOpen = ref(false)
const form = reactive<{ role: Role; disabled: boolean }>({ role: 'viewer', disabled: false })
const saving = ref(false)
const saveError = ref('')
const passwordOpen = ref(false)
const passwordTarget = ref<WebUser | null>(null)
let loadId = 0
async function load() {
  const id = ++loadId
  loading.value = true
  error.value = ''
  const params = new URLSearchParams({ page: String(page.value), size: '20', q: q.value.trim() })
  if (role.value) params.set('role', role.value)
  if (status.value) params.set('disabled', status.value)
  try {
    const result = await fetchUsers(params)
    if (id !== loadId) return
    rows.value = result.items; total.value = result.total
    if (!rows.value.length && total.value && page.value > 1) {
      page.value = Math.ceil(total.value / 20)
      await load()
    }
  } catch (e) { if (id === loadId) { rows.value = []; total.value = 0; error.value = (e as Error).message } }
  finally { if (id === loadId) loading.value = false }
}
function search() { page.value = 1; void load() }
function edit(user: WebUser) {
  editing.value = user
  form.role = user.role; form.disabled = user.disabled
  saveError.value = ''; editOpen.value = true
}
async function save() {
  if (!editing.value || saving.value) return
  saving.value = true
  saveError.value = ''
  try {
    const changed = form.role !== editing.value.role || form.disabled !== editing.value.disabled
    if (changed) {
      try {
        await ElMessageBox.confirm(`保存后「${editing.value.username}」需要重新登录。${form.disabled ? '禁用后将无法访问网站。' : ''}`, '确认账号变更', { confirmButtonText: '保存变更', cancelButtonText: '取消', type: 'warning' })
      } catch { return }
    }
    await updateUser(editing.value.id, form.role, form.disabled)
    editOpen.value = false
    ElMessage.success('账号设置已保存')
    await load()
  } catch (e) { saveError.value = (e as Error).message }
  finally { saving.value = false }
}
function reset(user: WebUser) { passwordTarget.value = user; passwordOpen.value = true }
const time = (value: string | null) => value ? new Date(value).toLocaleString('zh-CN') : '尚未登录'
onMounted(load)
</script>

<template>
  <section class="users-page">
    <div class="heading"><div><h2>网站用户</h2><p>管理可访问网站的账号、权限和登录状态。</p></div><el-tag type="info">共 {{ total }} 个账号</el-tag></div>
    <el-form class="filters" inline @submit.prevent="search">
      <el-form-item label="账号"><el-input v-model="q" placeholder="搜索账号" clearable :maxlength="64" @clear="search" /></el-form-item>
      <el-form-item label="角色"><el-select v-model="role" style="width: 150px" clearable placeholder="全部角色" @change="search"><el-option v-for="(label, key) in ROLE_LABELS" :key="key" :label="label" :value="key" /></el-select></el-form-item>
      <el-form-item label="状态"><el-select v-model="status" style="width: 120px" clearable placeholder="全部状态" @change="search"><el-option label="可登录" value="false" /><el-option label="已禁用" value="true" /></el-select></el-form-item>
      <el-form-item><el-button type="primary" native-type="submit" :loading="loading">查询</el-button><el-button :disabled="loading" @click="load">刷新</el-button></el-form-item>
    </el-form>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon role="alert" />
    <el-table v-loading="loading" :data="rows" row-key="id" empty-text="没有符合条件的网站账号">
      <el-table-column label="账号" min-width="180"><template #default="{ row }"><b>{{ row.username }}</b><el-tag v-if="row.id === auth.user?.id" size="small" class="self-tag">当前账号</el-tag></template></el-table-column>
      <el-table-column label="角色" min-width="130"><template #default="{ row }">{{ ROLE_LABELS[row.role as Role] ?? row.role }}</template></el-table-column>
      <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.disabled ? 'danger' : 'success'">{{ row.disabled ? '已禁用' : '可登录' }}</el-tag></template></el-table-column>
      <el-table-column label="最近登录" min-width="190"><template #default="{ row }">{{ time(row.last_login_at) }}</template></el-table-column>
      <el-table-column label="创建时间" min-width="190"><template #default="{ row }">{{ time(row.created_at) }}</template></el-table-column>
      <el-table-column label="操作" width="190" fixed="right"><template #default="{ row }"><template v-if="row.id !== auth.user?.id"><el-button link type="primary" @click="edit(row)">权限与状态</el-button><el-button link type="primary" @click="reset(row)">重置密码</el-button></template><span v-else class="muted">在右上角修改密码</span></template></el-table-column>
    </el-table>
    <el-pagination class="pagination" v-model:current-page="page" :page-size="20" :total="total" layout="total, prev, pager, next" @current-change="load" />
    <el-dialog v-model="editOpen" :title="`权限与状态 · ${editing?.username ?? ''}`" width="min(460px, 94vw)" :close-on-click-modal="false" :close-on-press-escape="!saving" :show-close="!saving" destroy-on-close>
      <el-alert v-if="saveError" :title="saveError" type="error" :closable="false" show-icon />
      <el-form label-position="top" @submit.prevent="save">
        <el-form-item label="网站角色"><el-select v-model="form.role" :disabled="saving"><el-option v-for="(label, key) in ROLE_LABELS" :key="key" :label="label" :value="key" /></el-select><span class="muted">{{ ROLE_HELP[form.role] }}</span></el-form-item>
        <el-form-item label="账号状态"><el-switch v-model="form.disabled" active-text="已禁用" inactive-text="可登录" :disabled="saving" /></el-form-item>
        <p class="muted">修改权限或状态后，该账号的现有登录会立即失效。</p>
        <div class="actions"><el-button :disabled="saving" @click="editOpen = false">取消</el-button><el-button type="primary" native-type="submit" :loading="saving">保存</el-button></div>
      </el-form>
    </el-dialog>
    <PasswordDialog v-model="passwordOpen" :target="passwordTarget" @saved="load" />
  </section>
</template>

<style scoped>
.heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 24px; }
h2 { margin: 0 0 8px; font-size: 22px; }
.heading p, .muted { color: var(--el-text-color-secondary); font-size: 13px; line-height: 1.7; }
.heading p { margin: 0; }
.filters { padding: 18px 18px 0; background: var(--el-fill-color-light); border-radius: 8px; margin-bottom: 20px; }
.self-tag { margin-left: 10px; }
.pagination, .actions { display: flex; justify-content: flex-end; margin-top: 20px; }
.el-alert { margin-bottom: 16px; }
</style>
