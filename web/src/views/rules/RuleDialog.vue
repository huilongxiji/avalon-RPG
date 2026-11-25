<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { RequestError } from '@/api/client'
import { checkRecord, emptyDocument, fetchManageMeta, saveRecord, TITLES, type Category, type ManageMeta, type RuleCheck, type RuleDocument, type RuleRecord } from '@/api/rulesManage'
import RuleFields from './RuleFields.vue'
import EffectFields from './EffectFields.vue'

const open = defineModel<boolean>({ required: true })
const props = defineProps<{ category: Category; record: RuleRecord | null; copy: boolean; readonly: boolean; versionId: number; draft: boolean }>()
const emit = defineEmits<{ saved: []; dirty: [value: boolean] }>()
const meta = ref<ManageMeta | null>(null)
const form = ref<RuleDocument>({})
const source = ref('')
const mode = ref('form')
const initial = ref('')
const busy = ref('')
const error = ref('')
const problems = ref<string[]>([])
const message = ref('')
const preview = ref<RuleCheck['preview']>()
const loading = ref(false)
const version = ref(0)
const beforeHash = ref<string | null>(null)
const key = ref<string | null>(null)
let loadId = 0
const dirty = computed(() => !props.readonly && (mode.value === 'json' ? source.value : JSON.stringify(form.value, null, 2)) !== initial.value)
watch(dirty, value => emit('dirty', value))
watch([form, source], () => { message.value = ''; preview.value = undefined }, { deep: true })
watch(open, async value => {
  if (!value) { ++loadId; emit('dirty', false); return }
  const id = ++loadId
  loading.value = true; error.value = ''; problems.value = []; message.value = ''; mode.value = 'form'; meta.value = null
  version.value = props.versionId; key.value = props.copy ? null : props.record?.key ?? null; beforeHash.value = props.copy ? null : props.record?.hash ?? null
  try {
    const m = await fetchManageMeta(props.draft)
    if (id !== loadId) return
    if (m.version_id !== version.value) throw new Error('规则版本已变化，请关闭窗口并刷新列表')
    meta.value = m
    form.value = props.record ? JSON.parse(JSON.stringify(props.record.data)) : emptyDocument(props.category, m)
    if (props.copy) {
      if (typeof form.value.id === 'number') form.value.id = m.next_ids[props.category]
      else if ('id' in form.value) form.value.id = ''
      if ('key' in form.value) form.value.key = ''
      if ('name' in form.value) form.value.name += '（副本）'
      if (props.category === 'monsters') form.value.no = null
      if ('output' in form.value) form.value.output = ''
    }
    source.value = initial.value = JSON.stringify(form.value, null, 2)
  } catch (e) { if (id === loadId) error.value = (e as Error).message }
  finally { if (id === loadId) loading.value = false }
})
function parsed(): RuleDocument {
  if (mode.value !== 'json') return JSON.parse(JSON.stringify(form.value))
  const value = JSON.parse(source.value)
  if (!value || Array.isArray(value) || typeof value !== 'object') throw new Error('规则内容必须是 JSON 对象')
  return value
}
function switchMode(next: string | number | boolean | undefined) {
  if (next === mode.value) return
  error.value = ''; problems.value = []
  try {
    if (next === 'form') {
      // 先由后端验证结构，避免错误 JSON 在表单中被静默丢弃。
      void fromJson()
    } else { source.value = JSON.stringify(form.value, null, 2); mode.value = 'json' }
  } catch (e) { error.value = (e as Error).message }
}
async function fromJson() {
  busy.value = '转换'
  try {
    let value = parsed()
    if (!props.readonly) value = (await checkRecord(props.category, key.value, version.value, beforeHash.value, value)).data
    form.value = value; mode.value = 'form'
  } catch (e) { failure(e) } finally { busy.value = '' }
}
function failure(e: unknown) {
  error.value = (e as Error).message
  problems.value = e instanceof RequestError ? e.problems : []
}
async function submit(check = false) {
  if (props.readonly || busy.value || !meta.value) return
  error.value = ''; problems.value = []; message.value = ''; busy.value = check ? '校验' : '保存'
  try {
    const value = parsed()
    if (check) {
      const checked = await checkRecord(props.category, key.value, version.value, beforeHash.value, value)
      message.value = checked.message; preview.value = checked.preview
    }
    else {
      await saveRecord(props.category, key.value, version.value, beforeHash.value, value)
      ElMessage.success('已保存到草稿，激活后生效'); initial.value = JSON.stringify(form.value, null, 2); open.value = false; emit('saved')
    }
  } catch (e) { failure(e) } finally { busy.value = '' }
}
async function close(done?: () => void) {
  if (busy.value) return
  if (dirty.value) {
    try { await ElMessageBox.confirm('尚有未保存的修改，确定放弃吗？', '关闭编辑', { confirmButtonText: '放弃修改', cancelButtonText: '继续编辑', type: 'warning' }) }
    catch { return }
  }
  if (done) done(); else open.value = false
}
</script>

<template>
  <el-dialog v-model="open" class="rule-dialog" style="max-height: 92vh; display: flex; flex-direction: column" :title="`${readonly ? '查看' : key === null ? '新建' : '编辑'}${TITLES[category]}${record ? ` · ${record.name}` : ''}`" width="min(1000px, 95vw)" top="4vh" :before-close="close" :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy" destroy-on-close>
    <el-skeleton v-if="loading" :rows="8" animated />
    <template v-else>
      <div class="editor-toolbar"><el-tag :type="draft ? 'warning' : 'info'">{{ draft ? '草稿' : '生效版本' }} {{ version }}</el-tag><el-radio-group :model-value="mode" :disabled="!!busy || !meta" @change="switchMode"><el-radio-button value="form">表单编辑</el-radio-button><el-radio-button value="json">JSON 源码</el-radio-button></el-radio-group></div>
      <div v-if="meta" class="editor-content">
        <el-input v-if="mode === 'json'" v-model="source" type="textarea" :rows="23" :readonly="readonly" :disabled="!!busy" spellcheck="false" aria-label="规则 JSON 源码" class="source" />
        <el-form v-else label-position="top" :disabled="readonly || !!busy" @submit.prevent="submit()">
          <EffectFields v-if="category === 'effects'" v-model="form" :meta="meta" :creating="key === null" />
          <RuleFields v-else v-model="form" :category="category" :meta="meta" :creating="key === null" />
        </el-form>
      </div>
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="result"><ul v-if="problems.length"><li v-for="(p, i) in problems" :key="i">{{ p }}</li></ul></el-alert>
      <el-alert v-if="message" :title="message" type="success" :closable="false" show-icon class="result" />
      <div v-if="preview" class="result"><b>效果预览</b><p>{{ preview.description || '未填写描述' }}</p><ul><li v-for="(line, i) in preview.logic" :key="i">{{ line }}</li></ul></div>
    </template>
    <template #footer><el-button :disabled="!!busy" @click="close()">{{ readonly ? '关闭' : '取消' }}</el-button><template v-if="!readonly"><el-button :loading="busy === '校验'" :disabled="loading || !meta || (!!busy && busy !== '校验')" @click="submit(true)">校验（不保存）</el-button><el-button type="primary" :loading="busy === '保存'" :disabled="loading || !meta || (!!busy && busy !== '保存')" @click="submit()">保存到草稿</el-button></template></template>
  </el-dialog>
</template>

<style scoped>
.editor-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; }
:global(.rule-dialog .el-dialog__body) { min-height: 0; overflow-y: auto; }
:global(.rule-dialog .el-dialog__header), :global(.rule-dialog .el-dialog__footer) { flex-shrink: 0; }
.editor-content { padding: 2px 8px 4px 2px; }
.source :deep(textarea) { font-family: ui-monospace, monospace; font-size: 13px; line-height: 1.6; }
.result { margin-top: 14px; max-height: 22vh; overflow: auto; }
ul { margin: 4px 0; padding-left: 18px; }
</style>
