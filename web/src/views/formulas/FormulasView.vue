<script setup lang="ts">
// 公式管理：新建、修改、删除公式（只改草稿，激活后生效）。每个公式显示中文名称，下面是原式
// 战斗内置的公式不能删除、不能改代号和变量名；新建的公式可以在别的公式里调用：代号(值, …)
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import DraftBar from '@/components/DraftBar.vue'
import FormulaBlock from '@/components/FormulaBlock.vue'
import FormulaEditDialog from './FormulaEditDialog.vue'
import { fetchFormulas, type FormulaRef } from '@/api/catalog'
import { deleteFormula, showError } from '@/api/edit'
import { useRulesStore } from '@/stores/rules'

const route = useRoute()
const rules = useRulesStore()
const formulas = ref<FormulaRef[]>([])
const loading = ref(true)
const error = ref('')
const text = ref('')
const kind = ref('all')
const editing = ref(false)
const current = ref<FormulaRef | null>(null)

async function load() {
  try {
    formulas.value = await fetchFormulas(rules.useDraft)
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await rules.refresh()
  await load()
  // 从装备详情跳过来时滚到对应的公式
  if (route.hash) {
    await nextTick()
    document.querySelector(decodeURIComponent(route.hash))?.scrollIntoView({ block: 'start' })
  }
})
watch(() => [rules.useDraft, rules.revision], load)

const titles = computed(() => Object.fromEntries(formulas.value.map((f) => [f.name, f.title || f.name])))
const shown = computed(() => {
  const t = text.value.trim()
  return formulas.value.filter((f) => {
    if (kind.value === 'builtin' && !f.required) return false
    if (kind.value === 'custom' && f.required) return false
    if (!t) return true
    return [f.name, f.title, f.description, f.readable, f.expr, ...Object.values(f.variables)].some((s) =>
      s.includes(t),
    )
  })
})

function edit(f: FormulaRef | null) {
  current.value = f
  editing.value = true
}

async function remove(f: FormulaRef) {
  try {
    await ElMessageBox.confirm(`删除公式「${f.title || f.name}」？`, '删除公式', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await deleteFormula(f.name)
    ElMessage.success('已从草稿里删除')
    await rules.changed()
  } catch (e) {
    await showError(e, '没有删除')
  }
}

async function onSaved() {
  await rules.changed()
}
</script>

<template>
  <div class="page">
    <DraftBar />
    <div class="bar">
      <el-input v-model="text" placeholder="搜索：名称、代号、说明、变量、原式" clearable class="search" />
      <el-radio-group v-model="kind" size="small">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="builtin">战斗内置</el-radio-button>
        <el-radio-button value="custom">自己新建的</el-radio-button>
      </el-radio-group>
      <span class="spacer" />
      <el-tooltip :disabled="rules.canEdit" :content="rules.whyNot" placement="bottom">
        <span><el-button type="primary" :disabled="!rules.canEdit" @click="edit(null)">+ 新建公式</el-button></span>
      </el-tooltip>
    </div>
    <div class="hint">
      战斗里每一步都是一个有名字的公式，装备详情的「伤害计算」里能看到每件装备用到哪些公式、按什么顺序算。
      新建的公式可以在别的公式里调用，写法：代号(值, 值…)。
    </div>
    <el-skeleton v-if="loading" :rows="10" animated />
    <el-result v-else-if="error" icon="error" title="读取公式失败" :sub-title="error" />
    <template v-else>
      <el-empty v-if="!shown.length" description="没有符合条件的公式" />
      <FormulaBlock v-for="f in shown" :key="f.name" :formula="f" :titles="titles">
        <template #actions>
          <el-tooltip :disabled="rules.canEdit" :content="rules.whyNot" placement="top">
            <span>
              <el-button size="small" link type="primary" :disabled="!rules.canEdit" @click="edit(f)">修改</el-button>
              <el-button
                v-if="!f.required"
                size="small"
                link
                type="danger"
                :disabled="!rules.canEdit"
                @click="remove(f)"
              >
                删除
              </el-button>
            </span>
          </el-tooltip>
        </template>
      </FormulaBlock>
    </template>
    <FormulaEditDialog v-model="editing" :formula="current" :all="formulas" @saved="onSaved" />
  </div>
</template>

<style scoped>
.page {
  max-width: 1100px;
}
.bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 6px;
}
.search {
  width: 320px;
}
.spacer {
  flex: 1;
}
.hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
  line-height: 1.6;
}
</style>
