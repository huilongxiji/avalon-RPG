<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import DraftBar from '@/components/DraftBar.vue'
import { request } from '@/api/client'
import { showError } from '@/api/edit'
import { useRulesStore } from '@/stores/rules'

type Setting = { key: string; value: number | Record<string, number | number[]>; description: string }
const rules = useRulesStore()
const settings = ref<Setting[]>([])
const form = reactive<Record<string, number>>({})
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const fields = [
  { key: 'days', label: '有效天数', group: '有效期与发卡奖励', setting: 'card_days', index: -1 },
  { key: 'grant_stamina', label: '发卡特殊体力', group: '有效期与发卡奖励', setting: 'card_grant', index: 0 },
  { key: 'grant_pity', label: '发卡保底', group: '有效期与发卡奖励', setting: 'card_grant', index: 1 },
  { key: 'daily_stamina', label: '每日普通体力', group: '每日签到奖励', setting: 'card_daily', index: 0 },
  { key: 'daily_pity', label: '每日保底', group: '每日签到奖励', setting: 'card_daily', index: 1 },
  { key: 'daily_tower', label: '每日额外免费爬塔', group: '每日签到奖励', setting: 'card_daily', index: 2 },
  ...[
    ['year_card_extra_kinds', '额外背包格数'], ['year_checkin_stamina_pct', '签到基础体力加成（%）'],
    ['year_exp_bonus_pct', '副本与爬塔经验加成（%）'], ['year_coin_bonus_pct', '副本与爬塔代币加成（%）'],
    ['year_equipment_drop_pct', '装备掉率加成（%）'], ['year_normal_weight_reduction_pct', '普通怪权重降低（%）'],
    ['year_cooldown_reduction_pct', '副本与爬塔冷却缩短（%）'],
  ].map(([key, label]) => ({ key: key!, label: label!, group: '有效期内加成', setting: key!, index: -2 })),
]
const groups = ['有效期与发卡奖励', '每日签到奖励', '有效期内加成']

async function load() {
  loading.value = true
  try {
    settings.value = await request<Setting[]>(`/api/v1/catalog/settings?draft=${rules.useDraft}`)
    for (const field of fields) {
      const value = settings.value.find(s => s.key === field.setting)!.value
      if (field.index === -2) form[field.key] = value as number
      else {
        const year = (value as Record<string, number | number[]>).year!
        form[field.key] = field.index === -1 ? year as number : (year as number[])[field.index]!
      }
    }
    error.value = ''
  } catch (e) { error.value = (e as Error).message }
  finally { loading.value = false }
}

async function save() {
  saving.value = true
  try {
    const changed: Setting[] = JSON.parse(JSON.stringify(settings.value.filter(s => fields.some(f => f.setting === s.key))))
    for (const field of fields) {
      const row = changed.find(s => s.key === field.setting)!
      if (field.index === -2) row.value = form[field.key]!
      else {
        const values = row.value as Record<string, number | number[]>
        if (field.index === -1) values.year = form[field.key]!
        else (values.year as number[])[field.index] = form[field.key]!
      }
    }
    await request('/api/v1/edit/draft/settings', { method: 'PUT', body: JSON.stringify(changed) })
    ElMessage.success('年卡设定已保存到草稿，激活后生效')
    await rules.changed()
  } catch (e) { await showError(e, '没有保存') }
  finally { saving.value = false }
}

onMounted(async () => { await rules.refresh(); await load() })
watch(() => [rules.useDraft, rules.revision], load)
</script>

<template>
  <div class="settings-page">
    <DraftBar />
    <div class="intro">
      <h2>年卡设定</h2>
      <p>发卡时领取即时奖励；每日奖励随当天签到领取一次。首次发卡时若当天已签到，会补发当日奖励。续卡会延长有效期，并再次发放发卡奖励。</p>
      <p>默认沿用原版实际代码：发卡 6000 特殊体力、200 保底；每日 30 普通体力、15 保底、2 次免费爬塔。</p>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-skeleton v-else-if="loading" :rows="10" animated />
    <el-form v-else label-position="top" :disabled="!rules.canEdit || saving">
      <div class="groups">
        <el-card v-for="group in groups" :key="group" shadow="never">
          <template #header>{{ group }}</template>
          <el-form-item v-for="field in fields.filter(f => f.group === group)" :key="field.key" :label="field.label">
            <el-input-number v-model="form[field.key]" :min="field.key === 'days' ? 1 : 0" :max="field.key.endsWith('_pct') ? 100 : 1000000000" :precision="0" controls-position="right" />
          </el-form-item>
        </el-card>
      </div>
      <p class="hint">普通体力受体力上限限制。装备掉率加成不含宝石、材料和道具；降低的普通怪权重分配给精英和 BOSS。免费爬塔次数在签到时发放。</p>
      <el-button type="primary" :loading="saving" :disabled="!rules.canEdit || !!error" @click="save">保存年卡设定到草稿</el-button>
      <span v-if="!rules.canEdit" class="hint"> {{ rules.whyNot }}</span>
    </el-form>
  </div>
</template>

<style scoped>
.settings-page { max-width: 1280px; margin: auto; }
.intro { margin: 24px 0; }
h2 { margin-bottom: 12px; }
p { line-height: 1.7; }
.groups { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }
.el-input-number { width: 100%; }
.hint { color: var(--el-text-color-secondary); font-size: 13px; }
</style>
