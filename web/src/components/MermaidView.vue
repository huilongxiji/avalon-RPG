<script setup lang="ts">
// 用 Mermaid 画流程图。Mermaid 比较大，第一次用到时才加载
import { onMounted, ref, watch } from 'vue'

const props = defineProps<{ source: string }>()
const box = ref<HTMLElement | null>(null)
const error = ref('')
const drawing = ref(true)

let ready: Promise<typeof import('mermaid').default> | null = null
let seq = 0

function load() {
  ready ??= import('mermaid').then(({ default: mermaid }) => {
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'strict',
      theme: 'default',
      fontFamily: '-apple-system, "PingFang SC", "Microsoft YaHei", sans-serif',
      flowchart: { htmlLabels: true, curve: 'basis', nodeSpacing: 28, rankSpacing: 36 },
    })
    return mermaid
  })
  return ready
}

async function draw() {
  drawing.value = true
  error.value = ''
  try {
    const mermaid = await load()
    const { svg } = await mermaid.render(`mermaid-${Date.now()}-${seq++}`, props.source)
    if (box.value) box.value.innerHTML = svg
  } catch (e) {
    error.value = `流程图画不出来：${(e as Error).message}`
  } finally {
    drawing.value = false
  }
}

onMounted(draw)
watch(() => props.source, draw)
</script>

<template>
  <div class="mermaid-wrap">
    <el-skeleton v-if="drawing" :rows="4" animated />
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <div ref="box" class="mermaid-box" />
  </div>
</template>

<style scoped>
.mermaid-wrap {
  overflow-x: auto;
}
.mermaid-box :deep(svg) {
  max-width: 100%;
  height: auto;
}
</style>
