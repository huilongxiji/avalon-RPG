<script setup lang="ts">
// 新建 / 修改公式（只改草稿）。原式边写边检查：写法对不对、读成中文是什么意思
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormulaDef, FormulaRef } from '@/api/catalog'
import { checkExpr, createFormula, showError, updateFormula, type ExprCheckResult } from '@/api/edit'

const props = defineProps<{ modelValue: boolean; formula: FormulaRef | null; all: FormulaRef[] }>()
const emit = defineEmits<{ 'update:modelValue': [v: boolean]; saved: [f: FormulaRef] }>()

const open = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})
const creating = computed(() => props.formula == null)
const locked = computed(() => !!props.formula?.required) // 战斗内置：不能改代号和变量名

const form = reactive({ name: '', title: '', description: '', expr: '', vars: [] as { key: string; label: string }[] })
const check = ref<ExprCheckResult | null>(null)
const checking = ref(false)
const saving = ref(false)
const exprBox = ref<{ textarea?: HTMLTextAreaElement } | null>(null)

watch(
  () => props.modelValue,
  (v) => {
    if (!v) return
    const f = props.formula
    form.name = f?.name ?? ''
    form.title = f?.title ?? ''
    form.description = f?.description ?? ''
    form.expr = f?.expr ?? ''
    form.vars = Object.entries(f?.variables ?? {}).map(([key, label]) => ({ key, label }))
    if (!f) form.vars = [{ key: 'x', label: '' }]
    check.value = null
    runCheck()
  },
)

let timer: ReturnType<typeof setTimeout> | undefined
watch(
  () => [form.expr, form.vars.map((v) => v.key + '=' + v.label).join('|')],
  () => {
    clearTimeout(timer)
    timer = setTimeout(runCheck, 300)
  },
)

async function runCheck() {
  if (!form.expr.trim()) {
    check.value = { ok: false, message: '请填写原式', readable: '' }
    return
  }
  checking.value = true
  try {
    check.value = await checkExpr({
      expr: form.expr,
      names: form.vars.map((v) => v.key).filter((k) => k),
      labels: Object.fromEntries(form.vars.filter((v) => v.key && v.label).map((v) => [v.key, v.label])),
      formulas: true,
    })
  } catch (e) {
    check.value = { ok: false, message: (e as Error).message, readable: '' }
  } finally {
    checking.value = false
  }
}

// 可以调用的其他公式（点一下插入到原式里）
const callable = computed(() => props.all.filter((f) => f.name !== props.formula?.name))
function insert(text: string) {
  const el = exprBox.value?.textarea
  const at = el?.selectionStart ?? form.expr.length
  form.expr = form.expr.slice(0, at) + text + form.expr.slice(el?.selectionEnd ?? at)
}
function callText(f: FormulaRef) {
  return `${f.name}(${Object.keys(f.variables).join(', ')})`
}

const FUNCTIONS: [string, string][] = [
  ['min(a, b)', '取小的'],
  ['max(a, b)', '取大的'],
  ['abs(x)', '绝对值'],
  ['floor(x)', '向下取整'],
  ['ceil(x)', '向上取整'],
  ['round(x)', '四舍五入'],
  ['sqrt(x)', '开平方'],
  ['clamp(x, 下限, 上限)', '限制在范围内'],
]

async function save() {
  const keys = form.vars.map((v) => v.key.trim())
  if (keys.some((k) => !k)) return ElMessage.warning('变量名不能为空')
  if (new Set(keys).size !== keys.length) return ElMessage.warning('变量名不能重复')
  const body: FormulaDef = {
    name: form.name.trim(),
    title: form.title.trim(),
    description: form.description.trim(),
    expr: form.expr.trim(),
    params: Object.fromEntries(form.vars.map((v) => [v.key.trim(), v.label.trim()])),
  }
  if (!body.name) return ElMessage.warning('请填写代号')
  saving.value = true
  try {
    const saved = props.formula ? await updateFormula(props.formula.name, body) : await createFormula(body)
    ElMessage.success('已保存到草稿')
    emit('saved', saved)
    open.value = false
  } catch (e) {
    await showError(e)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog v-model="open" :title="creating ? '新建公式' : `修改公式：${formula?.title || formula?.name}`" width="820px" top="5vh">
    <el-form label-width="80px">
      <el-form-item label="中文名称">
        <el-input v-model="form.title" maxlength="64" placeholder="例如：暴击后的伤害" />
      </el-form-item>
      <el-form-item label="代号" required>
        <el-input v-model="form.name" :disabled="locked" maxlength="64" placeholder="例如：翻倍（可以用中文，不能以数字开头）" />
        <div class="tip">
          {{ locked ? '战斗计算按这个代号调用它，不能改。' : '在别的公式里这样调用：代号(值, 值…)，例如 翻倍(x)。' }}
        </div>
      </el-form-item>
      <el-form-item label="说明">
        <el-input v-model="form.description" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="变量">
        <div class="vars">
          <div v-for="(v, i) in form.vars" :key="i" class="var-row">
            <el-input v-model="v.key" :disabled="locked" placeholder="变量名" class="var-key" />
            <el-input v-model="v.label" placeholder="中文说明，例如：攻击方等级" />
            <el-button v-if="!locked" link type="danger" @click="form.vars.splice(i, 1)">删除</el-button>
          </div>
          <el-button v-if="!locked" size="small" @click="form.vars.push({ key: '', label: '' })">+ 添加变量</el-button>
          <div v-else class="tip">战斗计算按这些变量名传值，变量名不能改，只能改中文说明。</div>
        </div>
      </el-form-item>
      <el-form-item label="原式" required>
        <el-input ref="exprBox" v-model="form.expr" type="textarea" :rows="4" class="mono" />
        <div class="check">
          <template v-if="checking">检查中……</template>
          <template v-else-if="check?.ok">
            <span class="ok">✓ 写法正确</span>
            <span v-if="check.readable" class="readable">读作：{{ check.readable }}</span>
          </template>
          <span v-else-if="check" class="bad">✗ {{ check.message }}</span>
        </div>
        <div class="helpers">
          <span class="label">函数：</span>
          <el-tooltip v-for="[text, label] in FUNCTIONS" :key="text" :content="label" placement="top">
            <el-tag size="small" effect="plain" class="chip" @click="insert(text)">{{ text }}</el-tag>
          </el-tooltip>
        </div>
        <div class="helpers">
          <span class="label">调用公式：</span>
          <el-tooltip v-for="f in callable" :key="f.name" :content="callText(f)" placement="top">
            <el-tag size="small" type="success" effect="plain" class="chip" @click="insert(callText(f))">
              {{ f.title || f.name }}
            </el-tag>
          </el-tooltip>
        </div>
        <div class="tip">
          运算：加 +、减 -、乘 *、除 /、整除 //、取余 %、乘方 **；比较 &lt; &gt; &lt;= &gt;= ==；
          并且 and、或者 or；条件写法：值1 if 条件 else 值2
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="open = false">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="check ? !check.ok : true" @click="save">保存到草稿</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.tip {
  width: 100%;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
.vars {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.var-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.var-key {
  width: 180px;
  flex-shrink: 0;
}
.mono :deep(textarea) {
  font-family: ui-monospace, Menlo, Consolas, monospace;
}
.check {
  width: 100%;
  margin-top: 4px;
  font-size: 13px;
  line-height: 1.6;
}
.ok {
  color: var(--el-color-success);
  margin-right: 12px;
}
.bad {
  color: var(--el-color-danger);
}
.readable {
  color: var(--el-text-color-regular);
}
.helpers {
  width: 100%;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
  margin-top: 6px;
}
.label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.chip {
  cursor: pointer;
}
</style>
