<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const username = ref('')
const password = ref('')
const busy = ref(false)
const error = ref(auth.error)
async function submit() {
  if (busy.value) return
  error.value = ''
  if (!username.value.trim() || !password.value) { error.value = '请填写账号和密码'; return }
  busy.value = true
  try {
    await auth.signIn(username.value.trim(), password.value)
    password.value = ''
    const next = typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'
    await router.replace(next.startsWith('/') && !next.startsWith('//') && !next.startsWith('/login') ? next : '/dashboard')
  } catch (e) { error.value = (e as Error).message }
  finally { busy.value = false }
}
</script>

<template>
  <main class="login-page">
    <section class="login-card">
      <div class="brand-mark" aria-hidden="true">A</div>
      <p class="eyebrow">AVALON</p>
      <h1>登录阿瓦隆管理后台</h1>
      <p class="intro">请使用管理员分配的账号登录。</p>
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon role="alert" />
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="账号">
          <el-input v-model="username" name="username" autocomplete="username" :maxlength="64" autofocus placeholder="输入账号" :disabled="busy" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="password" name="password" type="password" autocomplete="current-password" show-password :maxlength="128" placeholder="输入密码" :disabled="busy" />
        </el-form-item>
        <el-button class="login-button" type="primary" native-type="submit" :loading="busy">登录</el-button>
      </el-form>
      <p class="help">账号不可用或忘记密码，请联系管理员。</p>
    </section>
  </main>
</template>

<style scoped>
.login-page { min-height: 100%; display: grid; place-items: center; padding: 32px 20px; box-sizing: border-box; background: radial-gradient(ellipse at 15% 15%, #e2edff, transparent 55%), #f5f7fb; }
.login-card { width: 100%; max-width: 380px; padding: 36px; background: white; border: 1px solid #e8edf5; border-radius: 16px; box-shadow: 0 16px 60px #243e6a12; }
.brand-mark { display: grid; place-items: center; width: 46px; height: 46px; background: #245cc6; color: white; border-radius: 12px; font-size: 26px; font-weight: 700; }
.eyebrow { margin: 24px 0 8px; color: #66758d; letter-spacing: 3px; font-size: 12px; }
h1 { font-size: 24px; margin: 0 0 12px; color: #1f2d44; }
.intro, .help { color: #6b7689; font-size: 14px; line-height: 1.7; }
.intro { margin-bottom: 24px; }
.el-alert { margin-bottom: 20px; }
.login-button { width: 100%; margin-top: 8px; height: 40px; }
.help { margin: 24px 0 0; font-size: 12px; }
@media (max-width: 480px) { .login-card { padding: 24px; width: auto; } }
</style>
