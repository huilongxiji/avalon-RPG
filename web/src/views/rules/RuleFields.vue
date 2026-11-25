<script setup lang="ts">
import { computed } from 'vue'
import type { Category, ManageMeta, RuleDocument } from '@/api/rulesManage'
import DropFields from './DropFields.vue'
import StatFields from './StatFields.vue'
const form = defineModel<RuleDocument>({ required: true })
const props = defineProps<{ category: Category; meta: ManageMeta; creating: boolean }>()
const recipeChoices = computed(() => props.category === 'recipes' ? props.meta.items : props.meta.props)
</script>
<template>
  <template v-if="category === 'sets'">
    <el-form-item label="套装名称（改名会同步更新装备关联）" required><el-input v-model="form.name" :maxlength="64" /></el-form-item>
    <div v-for="(tier, i) in form.tiers" :key="i" class="block"><div class="row"><el-form-item label="件数" required><el-input-number v-model="tier.pieces" :min="1" :max="6" :precision="0" /></el-form-item><el-form-item label="档位效果" class="grow" required><el-select v-model="tier.effects" multiple filterable placeholder="选择效果"><el-option v-for="e in meta.effects" :key="e.key" :value="e.key" :label="`${e.name} · ${e.key}`" /></el-select></el-form-item><el-button link type="danger" @click="form.tiers.splice(i, 1)">删除档位</el-button></div></div>
    <el-button @click="form.tiers.push({ pieces: Math.min(6, form.tiers.length + 1), effects: [] })">添加档位</el-button>
  </template>
  <template v-else-if="category === 'monsters'">
    <div class="grid"><el-form-item label="怪物代号（保存后固定）" required><el-input v-model="form.id" :disabled="!creating" :maxlength="64" /></el-form-item><el-form-item label="名称" required><el-input v-model="form.name" :maxlength="64" /></el-form-item><el-form-item label="种类"><el-select v-model="form.kind"><el-option v-for="(label, key) in meta.kinds" :key="key" :value="key" :label="label" /></el-select></el-form-item><el-form-item label="等级"><el-input-number v-model="form.level" :min="1" :precision="0" /></el-form-item><el-form-item label="图鉴编号（可留空）"><el-input-number v-model="form.no" :min="0" :precision="0" :value-on-clear="null" /></el-form-item><el-form-item label="代币奖励"><el-input-number v-model="form.coins" :min="0" :precision="0" /></el-form-item><el-form-item label="经验奖励"><el-input-number v-model="form.exp" :min="0" :precision="0" /></el-form-item></div>
    <h3>战斗属性</h3><StatFields v-model="form.stats" :stats="meta.stats" />
    <el-form-item label="战斗效果" class="section"><el-select v-model="form.effects" multiple filterable><el-option v-for="e in meta.effects" :key="e.key" :value="e.key" :label="e.name" /></el-select></el-form-item>
    <DropFields v-model="form" :meta="meta" />
  </template>
  <template v-else-if="category === 'dungeons'">
    <div class="grid"><el-form-item label="副本编号（保存后固定）" required><el-input-number v-model="form.id" :min="1" :precision="0" :disabled="!creating" /></el-form-item><el-form-item label="副本名称" required><el-input v-model="form.name" :maxlength="64" /></el-form-item><el-form-item label="消耗体力"><el-input-number v-model="form.stamina" :min="0" :precision="0" /></el-form-item><el-form-item label="隐秘怪物"><el-select v-model="form.hidden_id" clearable filterable placeholder="无"><el-option v-for="m in meta.monsters" :key="m.key" :value="m.key" :label="`${m.name} · ${meta.kinds[m.kind!]}`" /></el-select></el-form-item><el-form-item label="隐秘怪物概率（%）"><el-input-number v-model="form.hidden_rate" :min="0" :max="100" :precision="0" /></el-form-item></div>
    <h3>遇怪列表</h3><div v-for="(entry, i) in form.encounters" :key="i" class="row"><el-select v-model="entry.monster_id" filterable placeholder="选择怪物" class="grow"><el-option v-for="m in meta.monsters" :key="m.key" :value="m.key" :label="m.name" /></el-select><el-input-number v-model="entry.weight" :min="0" :precision="0" aria-label="遇怪权重" /><el-button link type="danger" @click="form.encounters.splice(i, 1)">移除</el-button></div><el-button @click="form.encounters.push({ monster_id: '', weight: 10 })">添加遇怪</el-button>
  </template>
  <DropFields v-else-if="category === 'drops'" v-model="form" :meta="meta" />
  <template v-else-if="category === 'props'">
    <div class="grid"><el-form-item label="道具编号（保存后固定）" required><el-input-number v-model="form.id" :min="0" :precision="0" :disabled="!creating" /></el-form-item><el-form-item label="名称" required><el-input v-model="form.name" :maxlength="64" /></el-form-item><el-form-item label="分类"><el-input v-model="form.category" placeholder="道具 / 材料" /></el-form-item><el-form-item label="使用效果" required><el-select v-model="form.effect" filterable><el-option v-for="(label, key) in meta.prop_effects" :key="key" :value="key" :label="label" /></el-select></el-form-item><el-form-item label="效果数值"><el-input-number v-model="form.amount" :min="0" :precision="0" /></el-form-item><el-form-item label="购买价格"><el-input-number v-model="form.value" :min="0" :precision="0" /></el-form-item>
      <el-form-item v-if="form.effect === 'equip'" label="装备礼盒所属副本" required><el-select v-model="form.dungeon" filterable><el-option v-for="d in meta.dungeons" :key="d.key" :value="d.name" :label="d.name" /></el-select></el-form-item>
      <el-form-item v-else-if="form.effect === 'boss_choice'" label="自选礼盒所属 BOSS" required><el-select v-model="form.dungeon" filterable><el-option v-for="m in meta.monsters.filter(m => m.kind === 'boss')" :key="m.key" :value="m.name" :label="m.name" /></el-select></el-form-item>
      <el-form-item v-else label="来源说明"><el-input v-model="form.dungeon" /></el-form-item>
    </div><el-form-item label="道具说明"><el-input v-model="form.blurb" type="textarea" :rows="3" /></el-form-item>
  </template>
  <template v-else-if="category === 'recipes' || category === 'prop_recipes'">
    <div class="grid"><el-form-item label="配方编号（保存后固定）" required><el-input-number v-model="form.id" :min="0" :precision="0" :disabled="!creating" /></el-form-item><el-form-item label="成品" required><el-select v-model="form.output" filterable><el-option v-for="item in recipeChoices" :key="item.key" :value="item.key" :label="item.name" /></el-select></el-form-item><el-form-item label="每份成品数量"><el-input-number v-model="form.quantity" :min="1" :precision="0" /></el-form-item></div>
    <h3>每份消耗材料</h3><div v-for="(input, i) in form.inputs" :key="i" class="row"><el-select v-model="input.name" filterable class="grow" placeholder="选择材料"><el-option v-for="item in recipeChoices" :key="item.key" :value="item.key" :label="item.name" /></el-select><el-input-number v-model="input.quantity" :min="1" :precision="0" /><el-button link type="danger" @click="form.inputs.splice(i, 1)">移除</el-button></div><el-button @click="form.inputs.push({ name: '', quantity: 1 })">添加材料</el-button>
  </template>
  <template v-else-if="category === 'stacks'">
    <div class="grid"><el-form-item label="层数代号（表达式使用，保存后固定）" required><el-input v-model="form.key" :disabled="!creating" :maxlength="64" /></el-form-item><el-form-item label="名称" required><el-input v-model="form.name" :maxlength="64" /></el-form-item><el-form-item label="默认施加对象"><el-select v-model="form.owner"><el-option value="self" label="自己" /><el-option value="foe" label="对手" /></el-select></el-form-item><el-form-item label="层数上限（留空为不限）"><el-input-number v-model="form.max" :min="1" :precision="0" :value-on-clear="null" /></el-form-item><el-form-item label="由属性决定上限（可不选）"><el-select v-model="form.max_stat" clearable filterable @clear="form.max_stat = null"><el-option v-for="s in meta.stats" :key="s.key" :value="s.key" :label="s.name" /></el-select></el-form-item><el-form-item label="跨场保留"><el-switch v-model="form.carry" /></el-form-item><el-form-item label="世界 BOSS 免疫"><el-switch v-model="form.boss_immune" /></el-form-item></div>
  </template>
</template>
<style scoped>
.grid :deep(.el-select) { width: 100%; min-width: 0; }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 18px; }.row { display: flex; gap: 12px; align-items: center; margin-bottom: 12px; }.grow { flex: 1; min-width: 0; }.block { padding: 14px; background: var(--el-fill-color-light); border-radius: 8px; margin-bottom: 12px; }.block .row { margin: 0; }h3 { font-size: 15px; margin: 22px 0 14px; }.section { margin-top: 22px; }
@media(max-width: 600px) { .grid { grid-template-columns: 1fr; }.row { flex-wrap: wrap; } }
</style>
