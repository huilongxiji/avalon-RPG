<script setup lang="ts">
// 新建 / 修改装备（只改草稿）：基本信息、套装、全部属性。保存时后端会把整个草稿重新检查一遍，有问题不会保存
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchMeta, type EditMeta, type ItemDef, type ItemDetail } from '@/api/catalog'
import { fetchManageMeta, type Choice } from '@/api/rulesManage'
import { createItem, showError, updateItem } from '@/api/edit'

const props = defineProps<{ modelValue: boolean; item: ItemDef | null }>()
const emit = defineEmits<{ 'update:modelValue': [v: boolean]; saved: [detail: ItemDetail] }>()

const meta = ref<EditMeta | null>(null)
const saving = ref(false)
const effects = ref<Choice[]>([])
const loading = ref(false)
const form = reactive({
  name: '',
  slot: 'weapon',
  price: 0,
  damage_type: 'physical',
  main: '',
  sub: '',
  sponsor: false,
  retired: false,
  stats: {} as Record<string, number>,
  effects: [] as string[],
})

const open = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})
const creating = computed(() => props.item == null)

watch(
  () => props.modelValue,
  async (v) => {
    if (!v) return
    loading.value = true
    meta.value = null
    effects.value = []
    try {
      const [catalog, manage] = await Promise.all([fetchMeta(true), fetchManageMeta(true)])
      meta.value = catalog
      effects.value = manage.effects
    } catch (e) {
      await showError(e, '读取规则列表失败')
    } finally { loading.value = false }
    const i = props.item
    form.name = i?.name ?? ''
    form.slot = i?.slot ?? 'weapon'
    form.price = i?.price ?? 0
    form.damage_type = i?.damage_type ?? 'physical'
    form.main = i?.sets[0] ?? ''
    form.sub = i?.sets[1] ?? ''
    form.sponsor = i?.sponsor ?? false
    form.retired = i?.retired ?? false
    form.effects = [...(i?.effects ?? [])]
    form.stats = Object.fromEntries((meta.value?.stats ?? []).map((s) => [s.key, i?.stats[s.key] ?? 0]))
  },
)

async function save() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写名称')
    return
  }
  const body: ItemDef = {
    id: props.item?.id ?? 0,
    name: form.name.trim(),
    slot: form.slot,
    price: form.price || 0,
    damage_type: form.slot === 'weapon' ? form.damage_type : null,
    sets: [form.main, form.sub].filter((s) => s),
    effects: form.effects,
    sponsor: form.sponsor,
    retired: form.retired,
    stats: Object.fromEntries(Object.entries(form.stats).filter(([, v]) => v)),
  }
  saving.value = true
  try {
    const detail = props.item ? await updateItem(props.item.id, body) : await createItem(body)
    ElMessage.success(props.item ? '已保存到草稿' : `已新建，编号 ${detail.item.id}`)
    emit('saved', detail)
    open.value = false
  } catch (e) {
    await showError(e)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog v-model="open" :title="creating ? '新建装备' : `修改装备：${item?.name}`" width="820px" top="5vh">
    <el-form label-width="90px" :model="form" :disabled="loading || saving || !meta">
      <div class="row">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" maxlength="64" />
        </el-form-item>
        <el-form-item label="部位">
          <el-select v-model="form.slot">
            <el-option v-for="(label, key) in meta?.slots" :key="key" :label="label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="价格">
          <el-input-number v-model="form.price" :min="0" :controls="false" />
        </el-form-item>
        <el-form-item v-if="form.slot === 'weapon'" label="伤害类型">
          <el-select v-model="form.damage_type">
            <el-option v-for="(label, key) in meta?.damage_types" :key="key" :label="label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="主套装">
          <el-select v-model="form.main" clearable filterable placeholder="无">
            <el-option v-for="s in meta?.sets" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="副套装">
          <el-select v-model="form.sub" clearable filterable placeholder="无" :disabled="!form.main">
            <el-option v-for="s in meta?.sets.filter((x) => x !== form.main)" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="赞助宝石">
          <el-switch v-model="form.sponsor" />
        </el-form-item>
        <el-form-item v-if="!creating" label="下架">
          <el-switch v-model="form.retired" />
          <span class="tip">下架后不再掉落、不再出售，玩家已有的照常使用</span>
        </el-form-item>
      </div>
      <div class="section">属性（填 0 表示没有）</div>
      <div class="stats">
        <div v-for="s in meta?.stats" :key="s.key" class="stat">
          <span class="stat-name">{{ s.name }}</span>
          <el-input-number v-model="form.stats[s.key]" :controls="false" size="small" class="stat-input" />
          <span class="unit">{{ s.percent ? '%' : '' }}</span>
        </div>
      </div>
      <el-form-item label="自带效果" class="section">
        <el-select v-model="form.effects" multiple filterable placeholder="选择效果，可多选">
          <el-option v-for="effect in effects" :key="effect.key" :label="effect.name" :value="effect.key" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="open = false">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="loading || !meta" @click="save">保存到草稿</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  column-gap: 16px;
}
.section {
  margin: 8px 0;
  font-weight: 600;
  font-size: 13px;
}
.stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px 16px;
}
.stat {
  display: flex;
  align-items: center;
  gap: 6px;
}
.stat-name {
  width: 110px;
  font-size: 13px;
  text-align: right;
  color: var(--el-text-color-regular);
}
.stat-input {
  width: 100px;
}
.unit {
  width: 12px;
  font-size: 12px;
}
.tip {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
