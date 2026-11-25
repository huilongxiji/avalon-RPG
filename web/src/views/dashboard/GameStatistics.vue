<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import type { EChartsOption } from 'echarts'
import EChart from '@/components/EChart.vue'
import { request } from '@/api/client'

type Row = Record<string, string | number | null | Record<string, number>>
type Total = { currency: string; income: number; expense: number; net: number }
type Daily = { day: string; active_players: number; checkins: number; battles: number; data?: { challenges?: number } }
type Overview = { from: string; to: string; players: number; active_players: number; checkins: number; challenges: number; battles: number; pending: number; recorded_since: string | null; economy: Total[]; daily: Daily[] }
type DropTotal = { status: string; quantity_sum: number }
type Page = { total: number; items: Row[]; totals?: (Total | DropTotal)[]; outcomes?: { outcome: string; count: number }[]; damage?: { player: number | null; foe: number | null; rounds: number | null }[] }
const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul' }).format(new Date())
const range = ref<[string, string]>([today, today])
const openid = ref('')
const applied = ref({ from: today, to: today, openid: '' })
const source = ref('')
const currency = ref('')
const kind = ref('economy')
const page = ref(1)
const overview = ref<Overview | null>(null)
const result = ref<Page | null>(null)
const loading = ref(false)
const overviewError = ref('')
const ledgerError = ref('')
const filterError = ref('')
let sequence = 0
const currencies: Record<string, string> = { coins: '代币', world_coins: '世界币', bank: '银行代币', stamina: '普通体力', special_stamina: '特殊体力', exp: '累计经验', pity: '保底' }
const sources: Record<string, string> = {
  checkin: '签到', makeup: '补签', dungeon: '副本', tower: '爬塔', boss: '世界 BOSS', world_boss_settle: '世界 BOSS 结算',
  sell: '出售', sell_many: '批量出售', enhance: '强化', temper: '淬炼', craft: '装备合成', prop_craft: '道具合成',
  prop_use: '使用道具', shop_buy: '商城购买', redeem: '兑换码', buy: '市场购买', listing: '市场上架',
  cancel: '市场下架', expand: '背包扩容', decompose: '分解', admin_coins: '管理：代币',
  admin_world_coins: '管理：世界币', admin_stamina: '管理：体力', admin_exp: '管理：经验', admin_pity: '管理：保底',
  admin_card: '管理：赞助卡', admin_makeup: '管理：补签',
}
const outcomes: Record<string, string> = { win: '胜利', loss: '失败', draw: '平局', timeout: '回合上限' }
const cards = computed(() => overview.value ? [
  ['全服角色总数', overview.value.players], ['期间活跃玩家', overview.value.active_players],
  ['签到人次', overview.value.checkins], ['挑战次数', overview.value.challenges], ['战斗场次', overview.value.battles],
] : [])
const totals = computed(() => kind.value === 'economy' ? (result.value?.totals ?? []).filter((row): row is Total => 'currency' in row) : [])
const dropTotals = computed(() => (result.value?.totals ?? []).filter((row): row is DropTotal => 'quantity_sum' in row))
const damage = computed(() => result.value?.damage?.[0])
const triggers = computed(() => (result.value?.items ?? []).reduce((sum, row) => sum + Number(row.triggers ?? 0), 0))
const dailyOption = computed<EChartsOption>(() => ({
  color: ['#409eff', '#67c23a', '#e6a23c', '#8b5cf6'],
  tooltip: { trigger: 'axis', confine: true },
  legend: { data: ['活跃玩家', '签到人次', '挑战次数', '战斗场次'], bottom: 0 },
  grid: { left: 12, right: 16, top: 20, bottom: 55, containLabel: true },
  xAxis: { type: 'category', boundaryGap: false, data: (overview.value?.daily ?? []).map((day) => day.day) },
  yAxis: { type: 'value', minInterval: 1 },
  series: [
    { name: '活跃玩家', type: 'line', data: (overview.value?.daily ?? []).map((day) => day.active_players) },
    { name: '签到人次', type: 'line', data: (overview.value?.daily ?? []).map((day) => day.checkins) },
    { name: '挑战次数', type: 'line', data: (overview.value?.daily ?? []).map((day) => day.data?.challenges ?? 0) },
    { name: '战斗场次', type: 'line', data: (overview.value?.daily ?? []).map((day) => day.battles) },
  ],
}))
function time(value: unknown) { return value ? new Date(String(value)).toLocaleString('zh-CN', { timeZone: 'Asia/Seoul', hour12: false }) : '尚无记录' }
function label(value: unknown, map: Record<string, string>) { return map[String(value)] ?? String(value ?? '—') }
function applyFilters() {
  const [from, to] = range.value ?? []
  if (!from || !to || from > to || (Date.parse(to) - Date.parse(from)) / 86_400_000 > 365) {
    filterError.value = '请选择有效的起止日期，最多查询 366 天'
    return
  }
  filterError.value = ''
  applied.value = { from, to, openid: openid.value.trim() }
  overview.value = null
  void load(true)
}
async function load(reset = false) {
  if (reset) { page.value = 1; result.value = null }
  const ticket = ++sequence
  loading.value = true
  overviewError.value = ''
  ledgerError.value = ''
  try {
    const params = new URLSearchParams(applied.value)
    const details = new URLSearchParams(params)
    details.set('source', source.value)
    if (kind.value === 'economy') details.set('currency', currency.value)
    details.set('page', String(page.value))
    const [o, r] = await Promise.allSettled([
      request<Overview>(`/api/v1/stats/overview?${params}`),
      request<Page>(`/api/v1/stats/${kind.value}?${details}`),
    ])
    if (ticket !== sequence) return
    overview.value = o.status === 'fulfilled' ? o.value : null
    result.value = r.status === 'fulfilled' ? r.value : null
    if (o.status === 'rejected') overviewError.value = o.reason instanceof Error ? o.reason.message : '统计概览读取失败'
    if (r.status === 'rejected') ledgerError.value = r.reason instanceof Error ? r.reason.message : '流水读取失败'
  }
  finally { if (ticket === sequence) loading.value = false }
}
onBeforeUnmount(() => { sequence++ })
defineExpose({ refresh: () => load(), loading })
</script>

<template>
  <div class="stats-page">
    <div class="intro"><div><h2>游戏统计</h2><p>按游戏日期查询玩家活跃、资源收支及战斗记录。统计从接入后开始累计。</p></div></div>
    <div class="filters">
      <el-date-picker v-model="range" type="daterange" popper-class="statistics-date-picker" value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" :clearable="false" />
      <el-input v-model="openid" placeholder="玩家 OpenID（留空为全部）" clearable @keyup.enter="applyFilters" />
      <el-button type="primary" :loading="loading" @click="applyFilters">查询统计</el-button>
    </div>
    <el-alert v-if="filterError" :title="filterError" type="warning" :closable="false" />
    <el-alert v-if="overviewError" :title="overviewError" type="error" :closable="false" />
    <p class="applied-range">当前范围：{{ applied.from }} 至 {{ applied.to }} · {{ applied.openid ? `玩家 ${applied.openid}` : '全部玩家' }}</p>
    <el-skeleton v-if="loading && !overview" :rows="3" animated class="summary-loading" />
    <template v-if="overview">
      <div class="cards"><el-card v-for="[name, value] in cards" :key="String(name)" shadow="never"><span>{{ name }}</span><strong>{{ value }}</strong></el-card></div>
      <p class="hint">角色总数为当前全服人数；其余指标按日期与玩家筛选。活跃指有游戏操作记录的玩家，一次挑战可能产生多场战斗。</p>
      <el-alert v-if="overview.pending > 0" :title="`有 ${overview.pending} 条游戏记录等待计入统计，数据可能稍有延迟。`" type="warning" show-icon :closable="false" />
      <div class="summary-panels">
        <el-card shadow="never" header="每日活跃与战斗">
          <EChart v-if="overview.daily.length" :option="dailyOption" height="280px" />
          <el-empty v-else :image-size="65" description="这个范围内还没有每日统计" />
        </el-card>
        <el-card shadow="never" header="期间资源收支">
          <el-table :data="overview.economy" empty-text="这个范围内还没有资源变动" max-height="280">
            <el-table-column label="资源" min-width="100"><template #default="{ row }">{{ label(row.currency, currencies) }}</template></el-table-column>
            <el-table-column prop="income" label="收入" min-width="85" align="right" />
            <el-table-column prop="expense" label="支出" min-width="85" align="right" />
            <el-table-column label="净变动" min-width="90" align="right"><template #default="{ row }"><span :class="row.net > 0 ? 'income' : row.net < 0 ? 'expense' : ''">{{ row.net > 0 ? '+' : '' }}{{ row.net }}</span></template></el-table-column>
          </el-table>
        </el-card>
      </div>
      <p class="hint">全服首次记录：{{ time(overview.recorded_since) }}。历史存档不补造流水；趋势仅展示已有统计的日期。</p>
    </template>
    <el-card shadow="never" class="ledger">
      <template #header><h3>游戏流水明细</h3><p class="hint">以下来源和资源条件只筛选流水，不改变上方概览。</p></template>
      <el-alert v-if="ledgerError" :title="ledgerError" type="error" :closable="false" />
      <el-tabs v-model="kind" @tab-change="load(true)">
        <el-tab-pane label="收支流水" name="economy" /><el-tab-pane label="战斗流水" name="battles" />
        <el-tab-pane label="掉落流水" name="drops" /><el-tab-pane label="效果触发" name="effects" />
      </el-tabs>
      <div class="filters secondary">
        <el-select v-model="source" placeholder="全部来源" clearable filterable allow-create @change="load(true)"><el-option v-for="(name, key) in sources" :key="key" :label="name" :value="key" /></el-select>
        <el-select v-if="kind === 'economy'" v-model="currency" placeholder="全部资源" clearable @change="load(true)"><el-option v-for="(name, key) in currencies" :key="key" :label="name" :value="key" /></el-select>
      </div>
      <div v-if="totals.length" class="totals"><div v-for="total in totals" :key="total.currency"><b>{{ label(total.currency, currencies) }}</b> 收入 +{{ total.income }} / 支出 -{{ total.expense }} / 净变动 {{ total.net }}</div></div>
      <div v-if="result && kind === 'battles'" class="totals">
        <span>战斗 {{ result.total }} 场</span><span v-for="item in result.outcomes ?? []" :key="item.outcome">{{ label(item.outcome, outcomes) }} {{ item.count }} 场</span>
        <span>玩家伤害 {{ damage?.player ?? 0 }}</span><span>怪物伤害 {{ damage?.foe ?? 0 }}</span><span>平均回合 {{ damage?.rounds == null ? '—' : damage.rounds.toFixed(1) }}</span>
      </div>
      <div v-if="result && kind === 'drops'" class="totals"><span>掉落记录 {{ result.total }} 条</span><span v-for="item in dropTotals" :key="item.status">{{ item.status === 'sold' ? '自动出售' : '收入背包' }} {{ item.quantity_sum }} 件</span></div>
      <div v-if="result && kind === 'effects'" class="totals"><span>统计战斗 {{ result.total }} 场</span><span>效果 {{ result.items.length }} 种</span><span>触发 {{ triggers }} 次</span></div>
      <el-table v-loading="loading" :data="result?.items ?? []" empty-text="这个范围内还没有流水" stripe>
        <template v-if="kind !== 'effects'">
          <el-table-column label="时间" width="175"><template #default="{ row }">{{ time(row.at) }}</template></el-table-column>
          <el-table-column prop="openid" label="玩家" min-width="160" show-overflow-tooltip />
          <el-table-column label="来源" width="130"><template #default="{ row }">{{ label(row.source, sources) }}</template></el-table-column>
        </template>
        <template v-if="kind === 'economy'">
          <el-table-column label="资源" width="110"><template #default="{ row }">{{ label(row.currency, currencies) }}</template></el-table-column>
          <el-table-column label="变动" width="100"><template #default="{ row }"><span :class="row.delta > 0 ? 'income' : 'expense'">{{ row.delta > 0 ? '+' : '' }}{{ row.delta }}</span></template></el-table-column>
          <el-table-column prop="balance" label="变动后余额" min-width="120" />
          <el-table-column label="操作人" min-width="150" show-overflow-tooltip prop="actor" />
        </template>
        <template v-else-if="kind === 'battles'">
          <el-table-column prop="dungeon_id" label="副本" width="70" /><el-table-column prop="monster_id" label="怪物编号" min-width="100" />
          <el-table-column label="结果" width="90"><template #default="{ row }">{{ label(row.outcome, outcomes) }}</template></el-table-column>
          <el-table-column prop="rounds" label="回合" width="70" /><el-table-column prop="player_damage" label="玩家伤害" min-width="110" /><el-table-column prop="foe_damage" label="怪物伤害" min-width="110" />
        </template>
        <template v-else-if="kind === 'drops'">
          <el-table-column prop="item_name" label="物品" min-width="160" /><el-table-column prop="quantity" label="数量" width="70" />
          <el-table-column label="去向" width="100"><template #default="{ row }">{{ row.status === 'sold' ? '自动出售' : '收入背包' }}</template></el-table-column>
          <el-table-column prop="dungeon_id" label="副本" width="70" /><el-table-column prop="monster_id" label="怪物编号" min-width="100" />
        </template>
        <template v-else><el-table-column prop="effect" label="效果名称" /><el-table-column prop="triggers" label="触发次数" /></template>
        <el-table-column v-if="kind !== 'effects'" prop="rules_version" label="规则版本" width="90" />
      </el-table>
      <p class="hint" v-if="kind === 'economy'">累计经验包含已升级消耗的经验。流水按实际余额变化记录；强化净扣款按游戏实际结算金额入账。</p>
      <p class="hint" v-if="kind === 'drops'">记录副本、跨界副本和爬塔实际发放的战利品，包括背包满后自动出售的装备。未入包、未出售的失败发放不计入。</p>
      <p class="hint" v-if="kind === 'effects'">汇总玩家与怪物双方的效果触发次数，不代表伤害占比。</p>
      <el-pagination v-if="kind !== 'effects' && result" v-model:current-page="page" :page-size="50" :total="result.total" layout="total, prev, pager, next" @current-change="load()" />
    </el-card>
  </div>
</template>

<style scoped>
.stats-page { max-width: 1500px; margin: auto; }
.intro { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
h2 { margin: 0; font-size: 19px; }
h3 { margin: 0; font-size: 16px; }
.summary-loading { margin: 24px 0; }
.applied-range { margin-bottom: 0; }
.summary-panels { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); gap: 12px; margin-top: 16px; }
p, .hint { color: var(--el-text-color-secondary); font-size: 13px; line-height: 1.7; }
.filters { display: flex; flex-wrap: wrap; gap: 12px; margin: 16px 0; }
.filters .el-input { width: 290px; max-width: 100%; }.filters .el-select { width: 220px; max-width: 100%; }
.filters :deep(.el-date-editor) { max-width: 100%; box-sizing: border-box; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 24px 0 12px; }
.cards span { color: var(--el-text-color-secondary); font-size: 13px; }.cards strong { display: block; font-size: 30px; margin-top: 10px; }
.totals { display: flex; flex-wrap: wrap; gap: 10px 24px; padding: 12px; background: var(--el-fill-color-light); font-size: 13px; margin-bottom: 12px; }
.income { color: #198754; }.expense { color: #c33b32; }.el-pagination { justify-content: flex-end; margin-top: 20px; }
@media (max-width: 1050px) { .summary-panels { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 760px) { .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); } .filters :deep(.el-date-editor) { width: 100%; } .el-pagination { justify-content: flex-start; overflow-x: auto; } }
</style>

<style>
/* 日期弹层传送到 body；仅调整运行概览的手机双月日历。 */
@media (max-width: 640px) {
  .statistics-date-picker .el-date-range-picker { width: min(360px, calc(100vw - 24px)); }
  .statistics-date-picker .el-picker-panel__body { min-width: 0; max-height: min(70vh, 560px); overflow-y: auto; overflow-x: hidden; }
  .statistics-date-picker .el-date-range-picker__content { display: block; width: 100%; }
  .statistics-date-picker .el-date-range-picker__content.is-left { border-right: 0; border-bottom: 1px solid var(--el-border-color-light); }
}
</style>
