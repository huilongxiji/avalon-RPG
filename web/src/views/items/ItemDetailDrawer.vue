<script setup lang="ts">
// 装备详情（右侧抽屉，占屏幕 60%）：基本信息 / 属性 / 套装与效果 / 伤害计算（Mermaid 流程图 + 公式）
// 有草稿、在本机打开时可以修改、删除（只改草稿）
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import DamageFlowPanel from './DamageFlowPanel.vue'
import ItemEditDialog from './ItemEditDialog.vue'
import { DAMAGE_LABELS, fetchItem, formatStat, type EffectDetail, type ItemDetail } from '@/api/catalog'
import { deleteItem, showError } from '@/api/edit'
import { useRulesStore } from '@/stores/rules'

const props = defineProps<{ itemId: number | null }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const rules = useRulesStore()
const editing = ref(false)

const detail = ref<ItemDetail | null>(null)
const loading = ref(false)
const error = ref('')
const tab = ref('basic')
const nonZeroOnly = ref(true)

async function load(id: number | null, keepTab = false) {
  detail.value = null
  error.value = ''
  if (!keepTab) tab.value = 'basic'
  if (id == null) return
  loading.value = true
  try {
    detail.value = await fetchItem(id, rules.useDraft)
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

watch(() => props.itemId, (id) => load(id), { immediate: true })
watch(() => [rules.useDraft, rules.revision], () => load(props.itemId, true))

function onSaved(d: ItemDetail) {
  detail.value = d
  emit('changed')
}

async function onDelete() {
  const d = detail.value
  if (!d) return
  try {
    await ElMessageBox.confirm(
      `删除「${d.item.name}」？只有这个草稿里新建的装备能删除；已经上线的装备请用「修改」里的「下架」。`,
      '删除装备',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await deleteItem(d.item.id)
    ElMessage.success('已从草稿里删除')
    emit('changed')
    emit('close')
  } catch (e) {
    await showError(e, '没有删除')
  }
}

const visible = computed({
  get: () => props.itemId != null,
  set: (v: boolean) => {
    if (!v) emit('close')
  },
})

const stats = computed(() => {
  const all = detail.value?.stats ?? []
  return nonZeroOnly.value ? all.filter((s) => s.value !== 0) : all
})

// 这件装备涉及的所有效果（套装各档位 + 自带），公式页签里列出它们的表达式
const allEffects = computed<{ where: string; effect: EffectDetail }[]>(() => {
  const d = detail.value
  if (!d) return []
  const out: { where: string; effect: EffectDetail }[] = []
  for (const s of d.sets)
    for (const t of s.tiers) for (const e of t.effects) out.push({ where: `${s.name} · ${t.pieces} 件`, effect: e })
  for (const e of d.own_effects) out.push({ where: '装备自带', effect: e })
  return out
})
</script>

<template>
  <el-drawer v-model="visible" size="60%" :with-header="true" destroy-on-close>
    <template #header>
      <div v-if="detail" class="drawer-title">
        <span class="name">{{ detail.item.name }}</span>
        <el-tag size="small" type="info">#{{ detail.item.id }}</el-tag>
        <el-tag size="small" type="info">{{ detail.slot_label }}</el-tag>
        <el-tag v-if="detail.item.slot === 'weapon'" size="small">
          {{ DAMAGE_LABELS[detail.item.damage_type ?? 'physical'] }}
        </el-tag>
        <el-tag v-if="detail.item.retired" size="small" type="danger">已下架</el-tag>
        <el-tag v-if="rules.useDraft" size="small" type="warning" effect="plain">草稿</el-tag>
        <span class="spacer" />
        <el-tooltip :disabled="rules.canEdit" :content="rules.whyNot" placement="bottom">
          <span>
            <el-button size="small" type="primary" :disabled="!rules.canEdit" @click="editing = true">修改</el-button>
            <el-button size="small" type="danger" plain :disabled="!rules.canEdit" @click="onDelete">删除</el-button>
          </span>
        </el-tooltip>
      </div>
      <span v-else>装备详情</span>
    </template>

    <el-skeleton v-if="loading" :rows="8" animated />
    <el-result v-else-if="error" icon="error" title="读取失败" :sub-title="error" />
    <el-tabs v-else-if="detail" v-model="tab">
      <!-- 基本信息 -->
      <el-tab-pane label="基本信息" name="basic">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="编号">{{ detail.item.id }}</el-descriptions-item>
          <el-descriptions-item label="名称">{{ detail.item.name }}</el-descriptions-item>
          <el-descriptions-item label="部位">{{ detail.slot_label }}</el-descriptions-item>
          <el-descriptions-item label="价格">{{ detail.item.price }}</el-descriptions-item>
          <el-descriptions-item v-if="detail.item.slot === 'weapon'" label="伤害类型">
            {{ DAMAGE_LABELS[detail.item.damage_type ?? 'physical'] }}
          </el-descriptions-item>
          <el-descriptions-item label="主套装">{{ detail.item.sets[0] ?? '无' }}</el-descriptions-item>
          <el-descriptions-item label="副套装">{{ detail.item.sets[1] ?? '无' }}</el-descriptions-item>
          <el-descriptions-item label="赞助宝石">{{ detail.item.sponsor ? '是' : '否' }}</el-descriptions-item>
          <el-descriptions-item label="已下架">{{ detail.item.retired ? '是' : '否' }}</el-descriptions-item>
        </el-descriptions>
        <el-alert
          v-for="n in detail.notes"
          :key="n"
          :title="n"
          type="info"
          :closable="false"
          show-icon
          class="note"
        />
      </el-tab-pane>

      <!-- 属性 -->
      <el-tab-pane label="属性" name="stats">
        <div class="toolbar">
          <el-switch v-model="nonZeroOnly" active-text="只看不为 0 的属性" />
        </div>
        <el-table :data="stats" size="small" stripe>
          <el-table-column prop="name" label="属性" width="220" />
          <el-table-column label="数值">
            <template #default="{ row }">
              <span :class="{ zero: row.value === 0, negative: row.value < 0 }">{{ formatStat(row) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 套装与效果 -->
      <el-tab-pane label="套装与效果" name="effects">
        <el-empty v-if="!detail.sets.length && !detail.own_effects.length" description="这件装备没有套装和自带效果" />
        <section v-for="s in detail.sets" :key="s.name" class="set">
          <h3>
            {{ s.name }}
            <el-tag size="small" :type="s.role === 'main' ? 'success' : 'info'">
              {{ s.role === 'main' ? '主套装' : '副套装' }}
            </el-tag>
          </h3>
          <div v-if="s.members.length" class="members">同套装的装备：{{ s.members.join('、') }}</div>
          <div v-for="t in s.tiers" :key="t.pieces" class="tier">
            <div class="tier-head">{{ t.pieces }} 件</div>
            <div v-for="e in t.effects" :key="e.id" class="effect">
              <div class="effect-desc">{{ e.desc }}</div>
              <ol class="logic">
                <li v-for="(line, i) in e.logic" :key="i">{{ line }}</li>
              </ol>
            </div>
          </div>
        </section>
        <section v-if="detail.own_effects.length" class="set">
          <h3>装备自带效果</h3>
          <div v-for="e in detail.own_effects" :key="e.id" class="effect">
            <div class="effect-desc">{{ e.desc }}</div>
            <ol class="logic">
              <li v-for="(line, i) in e.logic" :key="i">{{ line }}</li>
            </ol>
          </div>
        </section>
      </el-tab-pane>

      <!-- 伤害计算 -->
      <el-tab-pane label="伤害计算" name="damage" lazy>
        <DamageFlowPanel :flows="detail.flows" :effects="allEffects" />
      </el-tab-pane>
    </el-tabs>
    <ItemEditDialog v-model="editing" :item="detail?.item ?? null" @saved="onSaved" />
  </el-drawer>
</template>

<style scoped>
.drawer-title {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}
.spacer {
  flex: 1;
}
.drawer-title .name {
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.note {
  margin-top: 12px;
}
.toolbar {
  margin-bottom: 8px;
}
.zero {
  color: var(--el-text-color-placeholder);
}
.negative {
  color: var(--el-color-danger);
}
.set {
  margin-bottom: 20px;
}
.set h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 0;
}
.members {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}
.tier {
  border-left: 3px solid var(--el-color-primary-light-5);
  padding-left: 12px;
  margin-bottom: 12px;
}
.tier-head {
  font-weight: 600;
  margin-bottom: 4px;
}
.effect {
  margin-bottom: 10px;
}
.effect-desc {
  line-height: 1.6;
}
.logic {
  margin: 6px 0 0;
  padding-left: 20px;
  font-size: 13px;
  color: var(--el-text-color-regular);
  line-height: 1.7;
}
</style>
