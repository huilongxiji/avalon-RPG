<script setup lang="ts">
// 一个公式：中文名称（标题），下面是原式（代码块）；再下面是说明、变量、中文读法、调用关系
import { computed } from 'vue'
import type { FormulaRef } from '@/api/catalog'

const props = defineProps<{ formula: FormulaRef; link?: boolean; titles?: Record<string, string> }>()
const variables = computed(() => Object.entries(props.formula.variables))
const nameOf = (n: string) => props.titles?.[n] || n
</script>

<template>
  <div :id="`formula-${formula.name}`" class="formula">
    <div class="head">
      <span class="title">{{ formula.title || formula.name }}</span>
      <span class="code-name">代号 {{ formula.name }}</span>
      <el-tag v-if="formula.required" size="small" type="info" effect="plain">战斗内置</el-tag>
      <span class="spacer" />
      <router-link v-if="link" class="go" :to="{ path: '/formulas', hash: `#formula-${formula.name}` }">
        到公式页修改
      </router-link>
      <slot name="actions" />
    </div>
    <pre class="code"><code>{{ formula.expr }}</code></pre>
    <div v-if="formula.description && formula.description !== formula.title" class="desc">
      {{ formula.description }}
    </div>
    <div v-if="variables.length" class="vars">
      <span class="label">变量：</span>
      <span v-for="[key, label] in variables" :key="key" class="var">
        <code>{{ key }}</code>{{ label ? ` ${label}` : '' }}
      </span>
    </div>
    <div v-if="formula.readable" class="readable"><span class="label">读作：</span>{{ formula.readable }}</div>
    <div v-if="formula.calls.length || formula.used_by.length" class="rel">
      <span v-if="formula.calls.length">调用了：{{ formula.calls.map(nameOf).join('、') }}</span>
      <span v-if="formula.used_by.length">被这些公式调用：{{ formula.used_by.map(nameOf).join('、') }}</span>
    </div>
  </div>
</template>

<style scoped>
.formula {
  padding: 12px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
  scroll-margin-top: 12px;
}
.head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.title {
  font-size: 15px;
  font-weight: 600;
}
.code-name {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.spacer {
  flex: 1;
}
.go {
  font-size: 12px;
  color: var(--el-color-primary);
}
.code {
  margin: 8px 0 0;
  padding: 8px 12px;
  background: #1f2430;
  color: #e6e6e6;
  border-radius: 6px;
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}
.desc {
  margin-top: 6px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.vars,
.readable,
.rel {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.7;
}
.vars {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
}
.var code {
  padding: 0 4px;
  background: var(--el-fill-color);
  border-radius: 3px;
}
.label {
  color: var(--el-text-color-secondary);
}
.rel {
  display: flex;
  gap: 16px;
  color: var(--el-text-color-secondary);
}
</style>
