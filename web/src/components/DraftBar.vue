<script setup lang="ts">
// 草稿条（装备页、公式页顶部）：生效版本、草稿、看哪一个；新建草稿 / 对比差异 / 校验 / 激活 / 放弃 / 历史版本
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRulesStore } from '@/stores/rules'
import {
  activateDraft,
  createDraft,
  discardDraft,
  fetchDiff,
  fetchVersions,
  rollbackTo,
  showError,
  showProblems,
  STATUS_LABELS,
  validateDraft,
  type DiffEntry,
  type VersionInfo,
} from '@/api/edit'

const rules = useRulesStore()
const busy = ref('')
const diffOpen = ref(false)
const diff = ref<DiffEntry[]>([])
const versionsOpen = ref(false)
const versions = ref<VersionInfo[]>([])

onMounted(() => rules.refresh())

const view = computed({
  get: () => (rules.viewDraft ? 'draft' : 'active'),
  set: (v: string) => {
    rules.viewDraft = v === 'draft'
  },
})

const CHANGE_LABELS = { added: '新增', removed: '删除', changed: '修改' } as const
const CHANGE_TAGS = { added: 'success', removed: 'danger', changed: 'warning' } as const

async function run(name: string, fn: () => Promise<void>) {
  busy.value = name
  try {
    await fn()
  } catch (e) {
    await showError(e, `${name}没有成功`)
  } finally {
    busy.value = ''
  }
}

const onCreate = () =>
  run('新建草稿', async () => {
    await createDraft()
    rules.viewDraft = true
    await rules.changed()
    ElMessage.success('已新建草稿。现在的修改都写在草稿里，玩家那边不受影响，激活后才生效')
  })

const onDiff = () =>
  run('对比差异', async () => {
    diff.value = await fetchDiff()
    diffOpen.value = true
  })

const onValidate = () =>
  run('校验', async () => {
    const r = await validateDraft()
    if (r.ok) ElMessage.success(`校验通过：规则编译正常，自检打了 ${r.battles} 场战斗，没有出错`)
    else await showProblems('校验没有通过', `发现 ${r.problems.length} 个问题，改好后才能激活：`, r.problems)
  })

async function onActivate() {
  try {
    await ElMessageBox.confirm(
      '激活后马上生效：之后的战斗、掉落都按草稿里的规则计算。以前的版本会保留，可以随时回滚。先会自动校验一遍。',
      '激活草稿',
      { confirmButtonText: '校验并激活', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  await run('激活', async () => {
    const v = await activateDraft()
    await rules.changed()
    ElMessage.success(`已激活，现在生效的是版本 ${v.id}`)
  })
}

async function onDiscard() {
  try {
    await ElMessageBox.confirm('草稿里的全部修改都会丢掉，不能恢复。', '放弃草稿', {
      confirmButtonText: '放弃',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  await run('放弃草稿', async () => {
    await discardDraft()
    await rules.changed()
    ElMessage.success('已放弃草稿')
  })
}

const onVersions = () =>
  run('读取历史版本', async () => {
    versions.value = await fetchVersions()
    versionsOpen.value = true
  })

async function onRollback(v: VersionInfo) {
  try {
    await ElMessageBox.confirm(`回滚后马上生效：规则回到版本 ${v.id} 的样子。`, '回滚', {
      confirmButtonText: '回滚',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  await run('回滚', async () => {
    await rollbackTo(v.id)
    versions.value = await fetchVersions()
    await rules.changed()
    ElMessage.success(`已回滚，现在生效的是版本 ${v.id}`)
  })
}

const time = (t: string | null) => (t ? new Date(t).toLocaleString('zh-CN') : '—')
</script>

<template>
  <div class="draft-bar">
    <span>生效版本：<b>{{ rules.state?.active?.id ?? '—' }}</b></span>
    <template v-if="rules.hasDraft">
      <el-tag type="warning">草稿 {{ rules.state?.draft?.id }} · 改了 {{ rules.state?.changes }} 处</el-tag>
      <el-radio-group v-model="view" size="small">
        <el-radio-button value="draft">看草稿</el-radio-button>
        <el-radio-button value="active">看生效版本</el-radio-button>
      </el-radio-group>
    </template>
    <span v-else class="muted">没有草稿</span>
    <span class="spacer" />
    <template v-if="rules.editable">
      <el-button v-if="!rules.hasDraft" type="primary" size="small" :loading="busy === '新建草稿'" @click="onCreate">
        新建草稿
      </el-button>
      <template v-else>
        <el-button size="small" :loading="busy === '对比差异'" @click="onDiff">对比差异</el-button>
        <el-button size="small" :loading="busy === '校验'" @click="onValidate">校验</el-button>
        <el-button v-if="rules.publishable" type="primary" size="small" :loading="busy === '激活'" @click="onActivate">激活</el-button>
        <el-button type="danger" plain size="small" :loading="busy === '放弃草稿'" @click="onDiscard">放弃草稿</el-button>
      </template>
    </template>
    <el-tooltip v-else content="当前账号只有查看权限" placement="bottom">
      <el-tag type="info">只能查看</el-tag>
    </el-tooltip>
    <el-button size="small" text :loading="busy === '读取历史版本'" @click="onVersions">历史版本</el-button>
    <el-tag v-if="rules.error" type="danger">{{ rules.error }}</el-tag>

    <el-dialog v-model="diffOpen" title="草稿和上一个版本的差异" width="760px">
      <el-empty v-if="!diff.length" description="还没有改动" />
      <el-table v-else :data="diff" size="small" max-height="60vh">
        <el-table-column prop="category_label" label="类别" width="80" />
        <el-table-column prop="name" label="名称" width="180" />
        <el-table-column label="改动" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="CHANGE_TAGS[row.change as DiffEntry['change']]">
              {{ CHANGE_LABELS[row.change as DiffEntry['change']] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="详情">
          <template #default="{ row }">
            <div v-for="(d, i) in row.details" :key="i">{{ d }}</div>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <el-dialog v-model="versionsOpen" title="历史版本" width="760px">
      <el-table :data="versions" size="small" max-height="60vh">
        <el-table-column prop="id" label="版本" width="60" />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">{{ STATUS_LABELS[row.status as VersionInfo['status']] }}</template>
        </el-table-column>
        <el-table-column prop="created_by" label="创建者" width="120" />
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ time(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="note" label="说明" />
        <el-table-column v-if="rules.publishable" label="" width="80">
          <template #default="{ row }">
            <el-button v-if="row.status === 'archived'" size="small" link type="primary" @click="onRollback(row)">
              回滚到这里
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<style scoped>
.draft-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 8px 12px;
  margin-bottom: 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  font-size: 13px;
}
.spacer {
  flex: 1;
}
.muted {
  color: var(--el-text-color-secondary);
}
</style>
