<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const submitting = ref(false)

function redirectTarget(): string {
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
  return redirect.startsWith('/') && !redirect.startsWith('//') ? redirect : '/'
}

async function submit() {
  submitting.value = true
  try {
    await auth.signIn(username.value.trim(), password.value)
    await router.replace(redirectTarget())
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="login-shell">
    <form class="login-card" @submit.prevent="submit">
      <div>
        <p class="eyebrow">Industrial Plugin Platform</p>
        <h2>平台登录</h2>
        <p class="muted">使用本地账号登录控制台，登录态由后端 Session 管理。</p>
      </div>
      <label>
        <span>用户名</span>
        <input v-model="username" autocomplete="username" />
      </label>
      <label>
        <span>密码</span>
        <input v-model="password" type="password" autocomplete="current-password" />
      </label>
      <p v-if="auth.loginError" class="error">{{ auth.loginError }}</p>
      <button type="submit" :disabled="submitting">{{ submitting ? '登录中' : '登录' }}</button>
    </form>
  </section>
</template>

<style scoped>
.login-shell { min-height: calc(100vh - 180px); display: grid; place-items: center; }
.login-card { width: min(420px, 100%); display: grid; gap: 14px; padding: 24px; background: #ffffff; border-radius: 12px; border: 1px solid #dbe4ef; box-shadow: 0 12px 36px rgba(15, 23, 42, 0.08); }
label { display: grid; gap: 8px; font-weight: 600; color: #1f2937; }
input { width: 100%; padding: 10px 12px; border: 1px solid #cdd8e5; border-radius: 8px; box-sizing: border-box; }
button { height: 42px; border: none; border-radius: 8px; background: #2563eb; color: #ffffff; font-weight: 600; cursor: pointer; }
button:disabled { opacity: 0.7; cursor: wait; }
.eyebrow { margin: 0 0 8px; color: #64748b; text-transform: uppercase; letter-spacing: 0.08em; font-size: 12px; }
.muted { color: #64748b; margin: 0; }
.error { color: #b91c1c; margin: 0; }
</style>
