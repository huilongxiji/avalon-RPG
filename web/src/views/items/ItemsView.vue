<script setup lang="ts">
// 装备与套装：按主套装分组的卡片，左侧筛选；点卡片打开详情（地址 /items/编号，可以单独打开、发给别人）
// 顶部草稿条：有草稿时默认看草稿，改过的装备卡片上有标记；在本机打开时可以新建、修改装备
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import DraftBar from '@/components/DraftBar.vue'
import ItemCard from './ItemCard.vue'
import ItemDetailDrawer from './ItemDetailDrawer.vue'
import ItemEditDialog from './ItemEditDialog.vue'
import { fetchItems, type ItemDetail, type ItemGroup, type ItemListResponse } from '@/api/catalog'
import { useRulesStore } from '@/stores/rules'

const route = useRoute()
const router = useRouter()

const data = ref<ItemListResponse | null>(null)
const loading = ref(true)
const error = ref('')
const filters = reactive({
  text: '',
  slots: [] as string[],
  damage: [] as string[],
  sets: [] as string[],
  marks: [] as string[],
})
const rules = useRulesStore()
const creating = ref(false)
const collapsed = reactive(new Set<string>())

const UNGROUPED = '未归入套装'

async function load() {
  try {
    data.value = await fetchItems(rules.useDraft)
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
})
watch(() => [rules.useDraft, rules.revision], load)

async function onChanged() {
  await rules.changed()
}

async function onCreated(d: ItemDetail) {
  await rules.changed()
  router.push(`/items/${d.item.id}`)
}

const allItems = computed(() => data.value?.groups.flatMap((g) => g.items) ?? [])
const slotOptions = computed(() => {
  const seen = new Map<string, string>()
  for (const i of allItems.value) seen.set(i.slot, i.slot_label)
  return [...seen.entries()]
})
const setOptions = computed(() => data.value?.groups.filter((g) => g.set).map((g) => g.set!.name) ?? [])

function groupName(g: ItemGroup): string {
  return g.set?.name ?? UNGROUPED
}

const visibleGroups = computed(() => {
  const text = filters.text.trim().toLowerCase()
  const out: ItemGroup[] = []
  for (const group of data.value?.groups ?? []) {
    let g = group
    if (filters.sets.length && !(g.set && filters.sets.includes(g.set.name))) {
      // 选了套装时：这个分组里属于所选套装（主或副）的装备也要显示
      const items = g.items.filter((i) => i.sets.some((s) => filters.sets.includes(s.name)))
      if (!items.length) continue
      g = { ...g, items }
    }
    const items = g.items.filter((i) => {
      if (filters.slots.length && !filters.slots.includes(i.slot)) return false
      if (filters.damage.length && !(i.damage_type && filters.damage.includes(i.damage_type))) return false
      if (filters.marks.length) {
        const marks = [i.changed && 'changed', i.added && 'added', i.retired && 'retired']
        if (!filters.marks.some((m) => marks.includes(m))) return false
      }
      if (!text) return true
      return (
        i.name.toLowerCase().includes(text) ||
        String(i.id) === text ||
        i.effect_brief.toLowerCase().includes(text) ||
        i.sets.some((s) => s.name.toLowerCase().includes(text))
      )
    })
    if (items.length) out.push({ ...g, items })
  }
  return out
})
const shownCount = computed(() => visibleGroups.value.reduce((n, g) => n + g.items.length, 0))

const selectedId = computed(() => {
  // 没有编号时参数是空字符串；装备编号可以是 0，所以不能用"是否为假"来判断
  const raw = route.params.id
  const text = Array.isArray(raw) ? raw[0] : raw
  if (text === undefined || text === '') return null
  const id = Number(text)
  return Number.isInteger(id) ? id : null
})

function openItem(id: number) {
  router.push(`/items/${id}`)
}
function closeItem() {
  router.push('/items')
}

function toggle(name: string) {
  if (collapsed.has(name)) collapsed.delete(name)
  else collapsed.add(name)
}
function setAll(open: boolean) {
  collapsed.clear()
  if (!open) for (const g of visibleGroups.value) collapsed.add(groupName(g))
}

async function jumpToSet(name: string) {
  collapsed.delete(name)
  if (!visibleGroups.value.some((g) => groupName(g) === name)) {
    filters.text = ''
    filters.slots = []
    filters.damage = []
    filters.sets = []
  }
  await nextTick()
  document.getElementById(`set-${name}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function resetFilters() {
  filters.text = ''
  filters.slots = []
  filters.damage = []
  filters.sets = []
  filters.marks = []
}
</script>

<template>
  <DraftBar />
  <div class="page">
    <aside class="filters">
      <el-input v-model="filters.text" placeholder="搜索：名称、编号、效果、套装" clearable />
      <div class="block">
        <div class="label">部位</div>
        <el-checkbox-group v-model="filters.slots">
          <el-checkbox v-for="[key, label] in slotOptions" :key="key" :value="key">{{ label }}</el-checkbox>
        </el-checkbox-group>
      </div>
      <div class="block">
        <div class="label">武器伤害类型</div>
        <el-checkbox-group v-model="filters.damage">
          <el-checkbox value="physical">物理</el-checkbox>
          <el-checkbox value="magic">法术</el-checkbox>
          <el-checkbox value="precision">精准</el-checkbox>
        </el-checkbox-group>
      </div>
      <div class="block">
        <div class="label">套装（可多选）</div>
        <el-select v-model="filters.sets" multiple filterable collapse-tags placeholder="全部套装" class="full">
          <el-option v-for="s in setOptions" :key="s" :label="s" :value="s" />
        </el-select>
      </div>
      <div class="block">
        <div class="label">标记</div>
        <el-checkbox-group v-model="filters.marks">
          <el-checkbox value="changed">草稿里改过</el-checkbox>
          <el-checkbox value="added">草稿里新建</el-checkbox>
          <el-checkbox value="retired">已下架</el-checkbox>
        </el-checkbox-group>
      </div>
      <el-button class="full" @click="resetFilters">清除筛选</el-button>
      <div class="summary">
        <div>显示的是：{{ rules.useDraft ? '草稿' : '生效版本' }} {{ data?.version_id ?? '—' }}</div>
        <div>显示 {{ shownCount }} / {{ data?.total ?? 0 }} 件</div>
      </div>
    </aside>

    <main class="content">
      <el-skeleton v-if="loading" :rows="10" animated />
      <el-result v-else-if="error" icon="error" title="读取装备失败" :sub-title="error" />
      <template v-else>
        <div class="bar">
          <el-button size="small" @click="setAll(true)">全部展开</el-button>
          <el-button size="small" @click="setAll(false)">全部折叠</el-button>
          <span class="spacer" />
          <el-tooltip :disabled="rules.canEdit" :content="rules.whyNot" placement="bottom">
            <span>
              <el-button size="small" type="primary" :disabled="!rules.canEdit" @click="creating = true">
                + 新建装备
              </el-button>
            </span>
          </el-tooltip>
        </div>
        <el-empty v-if="!visibleGroups.length" description="没有符合条件的装备" />
        <section v-for="g in visibleGroups" :id="`set-${groupName(g)}`" :key="groupName(g)" class="group">
          <header class="group-head" @click="toggle(groupName(g))">
            <el-icon class="arrow" :class="{ open: !collapsed.has(groupName(g)) }">▶</el-icon>
            <span class="group-name">{{ groupName(g) }}</span>
            <span class="count">· {{ g.items.length }} 件装备</span>
          </header>
          <div v-if="g.set" class="tiers">
            <div v-for="t in g.set.tiers" :key="t.pieces" class="tier">
              <span class="pieces">{{ t.pieces }} 件：</span>
              <span>{{ t.effects.map((e) => e.desc).join('；') }}</span>
            </div>
          </div>
          <div v-show="!collapsed.has(groupName(g))" class="grid">
            <ItemCard v-for="i in g.items" :key="i.id" :item="i" @open="openItem" @jump-set="jumpToSet" />
          </div>
        </section>
      </template>
    </main>

    <ItemDetailDrawer :item-id="selectedId" @close="closeItem" @changed="onChanged" />
    <ItemEditDialog v-model="creating" :item="null" @saved="onCreated" />
  </div>
</template>

<style scoped>
.page {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.filters {
  width: 220px;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.block .label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.full {
  width: 100%;
}
.summary {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.8;
}
.content {
  flex: 1;
  min-width: 0;
}
.bar {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}
.spacer {
  flex: 1;
}
.group {
  margin-bottom: 18px;
  scroll-margin-top: 8px;
}
.group-head {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 6px 0;
  user-select: none;
}
.arrow {
  font-size: 11px;
  transition: transform 0.15s;
}
.arrow.open {
  transform: rotate(90deg);
}
.group-name {
  font-size: 16px;
  font-weight: 600;
}
.count {
  color: var(--el-text-color-secondary);
}
.tiers {
  font-size: 13px;
  color: var(--el-text-color-regular);
  line-height: 1.7;
  margin: 0 0 8px 18px;
}
.pieces {
  font-weight: 600;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 12px;
}
</style>
