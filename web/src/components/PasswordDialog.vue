<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { changePassword, resetPassword, type WebUser } from '@/api/accounts'

const open = defineModel<boolean>({ required: true })
const props = defineProps<{ target?: WebUser | null }>()
const emit = defineEmits<{ saved: [] }>()
const current = ref('')
const password = ref('')
const confirm = ref('')
const error = ref('')
const busy = ref(false)
watch(open, () => { current.value = ''; password.value = ''; confirm.value = ''; error.value = '' })
async function save() {
  if (busy.value) return
  error.value = ''
  if (password.value.length < 12 || password.value.length > 128 || !password.value.trim()) {
    error.value = '新密码须为 12～128 个字符，不能全为空格'; return
  }
  if (password.value !== confirm.value) { error.value = '两次输入的新密码不一致'; return }
  if (!props.target && !current.value) { error.value = '请填写当前密码'; return }
  busy.value = true
  try {
    if (props.target) {
      await resetPassword(props.target.id, password.value)
      ElMessage.success('密码已重置，该账号需要重新登录')
      emit('saved')
      open.value = false
    } else {
      await changePassword(current.value, password.value)
      ElMessage.success('密码已修改，请重新登录')
      window.location.replace('/login')
    }
  } catch (e) { error.value = (e as Error).message }
  finally { busy.value = false }
}
</script>

<template>
  <el-dialog v-model="open" :title="target ? `重置密码 · ${target.username}` : '修改我的密码'" width="min(460px, 94vw)" :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy" destroy-on-close>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon role="alert" />
    <p class="note">保存后，该账号在所有设备上的登录都会失效。</p>
    <el-form label-position="top" @submit.prevent="save">
      <el-form-item v-if="!target" label="当前密码">
        <el-input v-model="current" type="password" show-password autocomplete="current-password" :maxlength="128" :disabled="busy" />
      </el-form-item>
      <el-form-item label="新密码">
        <el-input v-model="password" type="password" show-password autocomplete="new-password" placeholder="12～128 个字符" :maxlength="128" :disabled="busy" />
      </el-form-item>
      <el-form-item label="确认新密码">
        <el-input v-model="confirm" type="password" show-password autocomplete="new-password" :maxlength="128" :disabled="busy" />
      </el-form-item>
      <div class="actions">
        <el-button :disabled="busy" @click="open = false">取消</el-button>
        <el-button type="primary" native-type="submit" :loading="busy">保存密码</el-button>
      </div>
    </el-form>
  </el-dialog>
</template>

<style scoped>
.note { color: var(--el-text-color-secondary); line-height: 1.6; }
.actions { display: flex; justify-content: flex-end; }
</style>
