<script setup lang="ts">
// 装备详情"伤害计算"：每种伤害一张 Mermaid 流程图（方框是公式的中文名称），下面逐个列出公式（中文名称 + 原式）
import FormulaBlock from '@/components/FormulaBlock.vue'
import MermaidView from '@/components/MermaidView.vue'
import type { DamageFlow, EffectDetail } from '@/api/catalog'

defineProps<{ flows: DamageFlow[]; effects: { where: string; effect: EffectDetail }[] }>()
</script>

<template>
  <div>
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="按战斗里实际的计算顺序画的。蓝色方框是公式（显示中文名称），圆角框是参与计算的数值，菱形是判定，虚线是有条件时才走的步骤。"
      class="hint"
    />
    <section v-for="f in flows" :key="f.title" class="flow">
      <h3>{{ f.title }}</h3>
      <div v-if="f.description" class="desc">{{ f.description }}</div>
      <el-alert
        v-if="f.missing.length"
        type="error"
        :closable="false"
        :title="`规则里缺少这些公式：${f.missing.join('、')}`"
      />
      <MermaidView :source="f.mermaid" />
      <div class="formulas-head">用到的公式</div>
      <FormulaBlock v-for="r in f.formulas" :key="r.name" :formula="r" link />
    </section>

    <section v-if="effects.some((e) => e.effect.expressions.length)" class="flow">
      <h3>效果里的表达式</h3>
      <div class="desc">套装和装备自带效果里写的数值、条件（参数已代入数值）。</div>
      <div v-for="{ where, effect } in effects.filter((e) => e.effect.expressions.length)" :key="where + effect.id" class="expr-group">
        <div class="expr-head">{{ where }} · {{ effect.name }}</div>
        <div v-for="(x, i) in effect.expressions" :key="i" class="expr">
          <div class="where">{{ x.where }}</div>
          <pre class="code"><code>{{ x.source }}</code></pre>
          <div class="readable">读作：{{ x.readable }}</div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.hint {
  margin-bottom: 12px;
}
.flow {
  margin-bottom: 28px;
}
.flow h3 {
  margin: 0 0 4px;
}
.desc {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}
.formulas-head {
  margin-top: 12px;
  font-weight: 600;
  border-bottom: 1px solid var(--el-border-color);
  padding-bottom: 4px;
}
.expr-group {
  margin-bottom: 14px;
}
.expr-head {
  font-weight: 600;
  margin-bottom: 4px;
}
.expr {
  margin: 6px 0 10px 12px;
}
.where {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.code {
  margin: 4px 0 0;
  padding: 6px 10px;
  background: #1f2430;
  color: #e6e6e6;
  border-radius: 6px;
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-all;
}
.readable {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-regular);
}
</style>
