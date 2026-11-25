<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import DraftBar from '@/components/DraftBar.vue'
import { useRulesStore } from '@/stores/rules'
import { showError } from '@/api/edit'
import { deleteRecord, fetchRecords, HELP, TITLES, type Category, type RuleRecord, type RuleRecords } from '@/api/rulesManage'
import RuleDialog from './RuleDialog.vue'

const props = defineProps<{ category: Category }>()
const rules = useRulesStore()
const result = ref<RuleRecords | null>(null)
const loading = ref(false)
const error = ref('')
const query = ref('')
const page = ref(1)
const open = ref(false)
const selected = ref<RuleRecord | null>(null)
const copying = ref(false)
const dirty = ref(false)
const deleting = ref('')
let requestId = 0
const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return (result.value?.records ?? []).filter(r => !q || `${r.key} ${r.name} ${r.summary}`.toLowerCase().includes(q))
})
const rows = computed(() => filtered.value.slice((page.value - 1) * 20, page.value * 20))
const canEdit = computed(() => rules.canEdit && !!result.value?.draft && result.value.version_id === rules.state?.draft?.id)
async function load() {
  const id = ++requestId
  loading.value = true; error.value = ''
  try {
    const value = await fetchRecords(props.category, rules.useDraft)
    if (id === requestId) { result.value = value; page.value = Math.min(page.value, Math.max(1, Math.ceil(filtered.value.length / 20))) }
  } catch (e) { if (id === requestId) { result.value = null; error.value = (e as Error).message } }
  finally { if (id === requestId) loading.value = false }
}
function edit(row: RuleRecord | null, copy = false) { selected.value = row; copying.value = copy; open.value = true }
async function saved() { await rules.changed(); await load() }
async function remove(row: RuleRecord) {
  try { await ElMessageBox.confirm(`从草稿删除「${row.name}」？激活前不影响当前游戏。`, '删除规则', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }) }
  catch { return }
  deleting.value = row.key
  try { await deleteRecord(props.category, row, result.value!.version_id); ElMessage.success('已从草稿删除'); await saved() }
  catch (e) { await showError(e, '删除没有成功') }
  finally { deleting.value = '' }
}
async function beforeLeave() {
  if (open.value && dirty.value) {
    try { await ElMessageBox.confirm('编辑内容尚未保存，离开会放弃这些修改。', '离开此页', { confirmButtonText: '放弃并离开', cancelButtonText: '继续编辑', type: 'warning' }) }
    catch { return false }
  }
  open.value = false
}
onBeforeRouteLeave(beforeLeave)
onBeforeRouteUpdate(beforeLeave)
watch(() => props.category, () => { query.value = ''; result.value = null })
watch(query, () => { page.value = 1 })
watch(() => [props.category, rules.useDraft, rules.revision], () => { page.value = 1; void load() })
onMounted(async () => { await rules.refresh(); await load() })
</script>

<template>
  <section>
    <DraftBar />
    <div class="heading"><div><h2>{{ TITLES[category] }}管理</h2><p>{{ HELP[category] }}</p></div>
      <el-tooltip :disabled="canEdit" :content="rules.whyNot || '请刷新草稿'">
        <span><el-button v-if="category !== 'drops'" type="primary" :disabled="!canEdit || loading" @click="edit(null)">新建{{ TITLES[category] }}</el-button></span>
      </el-tooltip>
    </div>
    <div class="toolbar"><el-input v-model="query" clearable placeholder="搜索编号、名称或内容" class="search" /><el-button :loading="loading" @click="load">刷新列表</el-button><span class="muted">共 {{ filtered.length }} 条 · {{ result?.draft ? '草稿' : '生效版本' }} {{ result?.version_id ?? '—' }}</span></div>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <el-table v-loading="loading" :data="rows" row-key="key" empty-text="没有符合条件的规则" stripe>
      <el-table-column prop="key" label="编号 / 代号" min-width="150" show-overflow-tooltip />
      <el-table-column prop="name" label="名称" min-width="180" show-overflow-tooltip />
      <el-table-column prop="summary" label="内容" min-width="300" show-overflow-tooltip />
      <el-table-column label="引用" width="90"><template #default="{ row }"><el-popover v-if="row.references.length" placement="left" trigger="hover" :width="300"><template #reference><el-tag type="info">{{ row.references.length }} 处</el-tag></template><div v-for="ref in row.references" :key="ref">{{ ref }}</div></el-popover><span v-else class="muted">—</span></template></el-table-column>
      <el-table-column label="操作" width="210" fixed="right"><template #default="{ row }">
        <el-button link type="primary" @click="edit(row)">{{ canEdit ? '编辑' : '查看' }}</el-button>
        <template v-if="canEdit && category !== 'drops'">
          <el-button link type="primary" @click="edit(row, true)">复制</el-button>
          <el-tooltip :disabled="!row.protected_reason && !row.references.length" :content="row.protected_reason || '请先解除其他规则的引用'"><span><el-button link type="danger" :loading="deleting === row.key" :disabled="!!row.protected_reason || !!row.references.length || !!deleting" @click="remove(row)">删除</el-button></span></el-tooltip>
        </template>
      </template></el-table-column>
    </el-table>
    <el-pagination v-model:current-page="page" class="pagination" :total="filtered.length" :page-size="20" layout="total, prev, pager, next" />
    <RuleDialog v-model="open" :category="category" :record="selected" :copy="copying" :readonly="!canEdit" :version-id="result?.version_id ?? 0" :draft="!!result?.draft" @saved="saved" @dirty="dirty = $event" />
  </section>
</template>

<style scoped>
.heading { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin: 24px 0; }
h2 { margin: 0 0 10px; font-size: 22px; }
p, .muted { color: var(--el-text-color-secondary); font-size: 13px; line-height: 1.7; }
.toolbar { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-bottom: 18px; }
.search { max-width: 360px; }
.pagination { justify-content: flex-end; margin-top: 18px; }
.el-alert { margin-bottom: 16px; }
</style>
