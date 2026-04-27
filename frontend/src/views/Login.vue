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
  // 基础的安全过滤：确保只重定向到站内路径
  return redirect.startsWith('/') && !redirect.startsWith('//') ? redirect : '/'
}

async function submit() {
  submitting.value = true
  try {
    await auth.signIn(username.value.trim(), password.value)
    await router.replace(redirectTarget())
  } catch (e) {
    // 错误处理已由 authStore 捕获
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="login-shell industrial-theme">
    <div class="grid-overlay"></div>
    <div class="scanline"></div>

    <form class="login-card" @submit.prevent="submit">
      <header class="card-header">
        <span class="eyebrow"> 工业智能算法运行与管控平台</span>
        <h1 class="glow-text">身份验证</h1>
        <div class="status-bar">
          <span class="dot" :class="{ 'pulse': !submitting, 'loading': submitting }"></span>
          <span class="status-text">{{ submitting ? 'REQUESTING_ACCESS...' : 'SYSTEM_READY' }}</span>
        </div>
      </header>

      <div class="form-body">
        <div class="input-module">
          <label for="username">用户名</label>
          <div class="input-wrapper">
            <input 
              id="username"
              v-model="username" 
              autocomplete="username" 
              placeholder="ENTER_UID"
              required
            />
          </div>
        </div>

        <div class="input-module">
          <label for="password">密码</label>
          <div class="input-wrapper">
            <input 
              id="password"
              v-model="password" 
              type="password" 
              autocomplete="current-password" 
              placeholder="********"
              required
            />
          </div>
        </div>
      </div>

      <transition name="fade">
        <div v-if="auth.loginError" class="error-banner">
          <span class="warn-icon">!</span>
          <div class="error-msg">
            <strong>CRITICAL_FAILURE</strong>
            <p>{{ auth.loginError }}</p>
          </div>
        </div>
      </transition>

      <footer class="form-actions">
        <button type="submit" class="submit-btn" :disabled="submitting">
          <span class="btn-text">{{ submitting ? '验证中' : '登录' }}</span>
          <span class="btn-glitch"></span>
        </button>
      </footer>
    </form>
  </main>
</template>

<style scoped>
/* 核心颜色变量 */
.industrial-theme {
  --primary-cyan: #00f2ff;
  --bg-dark: #020b12;
  --card-bg: rgba(5, 22, 36, 0.95);
  --input-bg: rgba(0, 0, 0, 0.4);
  --border-cyan: rgba(0, 242, 255, 0.3);
  --error-red: #ff4d4d;
}

.login-shell {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-dark);
  position: relative;
  overflow: hidden;
  font-family: 'Inter', 'Fira Code', monospace;
}

/* 背景装饰 */
.grid-overlay {
  position: absolute; inset: 0;
  background-image: linear-gradient(var(--border-cyan) 1px, transparent 1px),
    linear-gradient(90deg, var(--border-cyan) 1px, transparent 1px);
  background-size: 50px 50px;
  opacity: 0.1;
  pointer-events: none;
}

.scanline {
  position: absolute; inset: 0;
  background: linear-gradient(to bottom, transparent 50%, rgba(0, 242, 255, 0.02) 50%);
  background-size: 100% 4px;
  pointer-events: none;
}

/* 登录卡片 */
.login-card {
  position: relative;
  width: min(460px, 90vw);
  background: var(--card-bg);
  border: 1px solid var(--border-cyan);
  padding: 40px;
  clip-path: polygon(0 0, 100% 0, 100% calc(100% - 20px), calc(100% - 20px) 100%, 0 100%);
  box-shadow: 0 0 50px rgba(0, 0, 0, 0.5), 0 0 20px rgba(0, 242, 255, 0.1);
}

.card-header { margin-bottom: 30px; }
.eyebrow { font-size: 10px; color: var(--primary-cyan); letter-spacing: 3px; font-weight: bold; }
.glow-text { 
  font-size: 1.8rem; margin: 10px 0; color: #fff;
  text-shadow: 0 0 15px rgba(0, 242, 255, 0.4);
}

.status-bar { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--primary-cyan); opacity: 0.8; }
.dot { width: 6px; height: 6px; background: var(--primary-cyan); border-radius: 50%; }
.dot.pulse { animation: pulse 2s infinite; }
.dot.loading { animation: blink 0.5s infinite; background: #fff; }

/* 表单输入 */
.form-body { display: grid; gap: 24px; }
.input-module { display: grid; gap: 8px; }
.input-module label { font-size: 11px; color: var(--primary-cyan); font-weight: bold; letter-spacing: 1px; }

.input-wrapper {
  position: relative;
  background: var(--input-bg);
  border-bottom: 2px solid var(--border-cyan);
  transition: all 0.3s ease;
}

.input-wrapper:focus-within {
  border-bottom-color: var(--primary-cyan);
  background: rgba(0, 242, 255, 0.05);
  box-shadow: 0 5px 15px rgba(0, 242, 255, 0.1);
}

input {
  width: 100%;
  padding: 14px;
  background: transparent;
  border: none;
  color: #fff;
  font-family: inherit;
  outline: none;
}

input::placeholder { color: rgba(255, 255, 255, 0.2); font-size: 13px; }

/* 错误处理 */
.error-banner {
  margin-top: 20px;
  background: rgba(255, 77, 77, 0.1);
  border: 1px solid var(--error-red);
  padding: 12px;
  display: flex; gap: 12px; align-items: center;
}
.warn-icon {
  background: var(--error-red); color: #000;
  width: 20px; height: 20px; display: flex; align-items: center; justify-content: center;
  font-weight: bold; font-size: 14px;
}
.error-msg strong { font-size: 10px; color: var(--error-red); display: block; }
.error-msg p { margin: 0; font-size: 13px; color: #ffbaba; }

/* 提交按钮 */
.form-actions { margin-top: 40px; text-align: center; }
.submit-btn {
  width: 100%;
  padding: 16px;
  background: var(--primary-cyan);
  color: #000;
  border: none;
  font-weight: 800;
  letter-spacing: 2px;
  cursor: pointer;
  clip-path: polygon(5% 0, 100% 0, 100% 70%, 95% 100%, 0 100%, 0 30%);
  transition: all 0.2s ease;
}

.submit-btn:hover:not(:disabled) {
  filter: brightness(1.2);
  transform: translateY(-2px);
  box-shadow: 0 5px 20px rgba(0, 242, 255, 0.4);
}

.submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.muted-hint { margin-top: 15px; font-size: 10px; color: rgba(255, 255, 255, 0.3); letter-spacing: 1px; }

/* 动画 */
@keyframes pulse {
  0% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(1.2); }
  100% { opacity: 1; transform: scale(1); }
}
@keyframes blink {
  50% { opacity: 0; }
}
</style>