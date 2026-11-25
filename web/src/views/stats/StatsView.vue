<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { request } from '@/api/client'

type Row = Record<string, string | number | null | Record<string, number>>
type Total = { currency: string; income: number; expense: number; net: number }
type Overview = { players: number; active_players: number; checkins: number; challenges: number; battles: number; pending: number; recorded_since: string | null; economy: Total[] }
type Page = { total: number; items: Row[]; totals?: Total[] }
const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul' }).format(new Date())
const range = ref<[string, string]>([today, today])
const openid = ref('')
const source = ref('')
const currency = ref('')
const kind = ref('economy')
const page = ref(1)
const overview = ref<Overview | null>(null)
const result = ref<Page | null>(null)
const loading = ref(false)
const error = ref('')
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
  ['角色总数', overview.value.players], ['期间活跃玩家', overview.value.active_players],
  ['签到人次', overview.value.checkins], ['挑战次数', overview.value.challenges], ['战斗场次', overview.value.battles],
] : [])
const totals = computed(() => kind.value === 'economy' ? result.value?.totals ?? [] : [])
function time(value: unknown) { return value ? new Date(String(value)).toLocaleString('zh-CN', { timeZone: 'Asia/Seoul', hour12: false }) : '尚无记录' }
function label(value: unknown, map: Record<string, string>) { return map[String(value)] ?? String(value ?? '—') }
async function load(reset = false) {
  if (reset) page.value = 1
  const ticket = ++sequence
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({ from: range.value[0], to: range.value[1], openid: openid.value.trim() })
    const details = new URLSearchParams(params)
    details.set('source', source.value)
    if (kind.value === 'economy') details.set('currency', currency.value)
    details.set('page', String(page.value))
    const [o, r] = await Promise.all([
      request<Overview>(`/api/v1/stats/overview?${params}`),
      request<Page>(`/api/v1/stats/${kind.value}?${details}`),
    ])
    if (ticket !== sequence) return
    overview.value = o
    result.value = r
  } catch (e) { if (ticket === sequence) { error.value = (e as Error).message; result.value = null; overview.value = null } }
  finally { if (ticket === sequence) loading.value = false }
}
onMounted(() => load())
</script>

<template>
  <div class="stats-page">
    <div class="intro"><div><h2>统计流水</h2><p>按游戏日期（UTC+9）查询。统计从接入后开始累计，历史存档不补造流水。</p></div><el-button :loading="loading" @click="load()">刷新</el-button></div>
    <div class="filters">
      <el-date-picker v-model="range" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" :clearable="false" />
      <el-input v-model="openid" placeholder="玩家 OpenID（留空为全部）" clearable @keyup.enter="load(true)" />
      <el-button type="primary" @click="load(true)">查询</el-button>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <template v-if="overview">
      <div class="cards"><el-card v-for="[name, value] in cards" :key="String(name)" shadow="never"><span>{{ name }}</span><strong>{{ value }}</strong></el-card></div>
      <p class="hint">首次记录：{{ time(overview.recorded_since) }} · 待写入统计库：{{ overview.pending }} 条。一次爬塔或连战可产生多场战斗；查询会显示已完成投递的流水。</p>
    </template>
    <el-card shadow="never" class="ledger">
      <el-tabs v-model="kind" @tab-change="load(true)">
        <el-tab-pane label="收支流水" name="economy" /><el-tab-pane label="战斗流水" name="battles" />
        <el-tab-pane label="掉落流水" name="drops" /><el-tab-pane label="效果触发" name="effects" />
      </el-tabs>
      <div class="filters secondary">
        <el-select v-model="source" placeholder="全部来源" clearable filterable allow-create @change="load(true)"><el-option v-for="(name, key) in sources" :key="key" :label="name" :value="key" /></el-select>
        <el-select v-if="kind === 'economy'" v-model="currency" placeholder="全部资源" clearable @change="load(true)"><el-option v-for="(name, key) in currencies" :key="key" :label="name" :value="key" /></el-select>
      </div>
      <div v-if="totals.length" class="totals"><div v-for="total in totals" :key="total.currency"><b>{{ label(total.currency, currencies) }}</b> 收入 +{{ total.income }} / 支出 -{{ total.expense }} / 净变动 {{ total.net }}</div></div>
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
        <template v-else><el-table-column prop="effect" label="效果代号" /><el-table-column prop="triggers" label="触发次数" /></template>
        <el-table-column v-if="kind !== 'effects'" prop="rules_version" label="规则版本" width="90" />
      </el-table>
      <p class="hint" v-if="kind === 'economy'">累计经验包含已升级消耗的经验。流水按实际余额变化记录；强化净扣款按游戏实际结算金额入账。</p>
      <p class="hint" v-if="kind === 'drops'">记录副本、跨界副本和爬塔实际发放的战利品，包括背包满后自动出售的装备。未入包、未出售的失败发放不计入。</p>
      <p class="hint" v-if="kind === 'effects'">按战斗引擎的效果触发次数统计，不代表伤害占比。</p>
      <el-pagination v-if="kind !== 'effects' && result" v-model:current-page="page" :page-size="50" :total="result.total" layout="total, prev, pager, next" @current-change="load()" />
    </el-card>
  </div>
</template>

<style scoped>
.stats-page { max-width: 1500px; margin: auto; }
.intro { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
h2 { margin: 0 0 12px; }
p, .hint { color: var(--el-text-color-secondary); font-size: 13px; line-height: 1.7; }
.filters { display: flex; flex-wrap: wrap; gap: 12px; margin: 16px 0; }
.filters .el-input { width: 290px; }.filters .el-select { width: 220px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 24px 0 12px; }
.cards span { color: var(--el-text-color-secondary); font-size: 13px; }.cards strong { display: block; font-size: 30px; margin-top: 10px; }
.totals { display: flex; flex-wrap: wrap; gap: 10px 24px; padding: 12px; background: var(--el-fill-color-light); font-size: 13px; margin-bottom: 12px; }
.income { color: #198754; }.expense { color: #c33b32; }.el-pagination { justify-content: flex-end; margin-top: 20px; }
</style>
