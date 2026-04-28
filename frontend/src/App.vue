<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter, RouterLink, RouterView } from 'vue-router'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const showLoginPage = computed(() => route.path === '/login')
const can = (permission: string) => auth.can(permission)

async function signOut() {
  await auth.signOut()
  if (auth.securityEnabled) {
    await router.replace('/login')
  }
}

// 响应式比例计算
const designWidth = 1920
const baseFontSize = 16
const setRem = () => {
  const clientWidth = document.documentElement.clientWidth || window.innerWidth
  const scale = clientWidth / designWidth
  const fontSize = Math.max(baseFontSize * scale, 12)
  document.documentElement.style.fontSize = fontSize + 'px'
}

onMounted(() => {
  setRem()
  window.addEventListener('resize', setRem)
})

onUnmounted(() => {
  window.removeEventListener('resize', setRem)
})
</script>

<template>
  <div class="fui-shell">
    <header class="fui-topbar">
      <nav v-if="!showLoginPage" class="fui-nav-menu">
        <RouterLink v-if="can('package.read')" to="/" class="nav-item">首页</RouterLink>

        <div v-if="can('package.read')" class="fui-dropdown">
          <span class="fui-dropdown-label">插件中心</span>
          <div class="fui-dropdown-content">
            <RouterLink to="/packages/upload">插件上传</RouterLink>
          </div>
        </div>

        <div v-if="can('package.read')" class="fui-dropdown">
          <span class="fui-dropdown-label">资产管理</span>
          <div class="fui-dropdown-content">
            <RouterLink to="/packages">插件管理</RouterLink>
            <RouterLink to="/models">模型管理</RouterLink>
          </div>
        </div>

        <div v-if="can('datasource.read') || can('instance.read')" class="fui-dropdown">
          <span class="fui-dropdown-label">数智建模</span>
          <div class="fui-dropdown-content">
            <RouterLink v-if="can('datasource.read')" to="/data-sources">数据源管理</RouterLink>
            <RouterLink v-if="can('instance.read')" to="/instances">实例管理</RouterLink>
            <RouterLink v-if="can('instance.read')" to="/instances/model-binding">模型绑定</RouterLink>
          </div>
        </div>

        <div v-if="can('run.read') || can('system.read')" class="fui-dropdown">
          <span class="fui-dropdown-label">运行监控</span>
          <div class="fui-dropdown-content">
            <RouterLink v-if="can('run.read')" to="/runs">运行记录</RouterLink>
            <RouterLink v-if="can('system.read')" to="/runtime-diagnostics">运行诊断</RouterLink>
          </div>
        </div>

        <div v-if="can('system.read') || can('user.read')" class="fui-dropdown">
          <span class="fui-dropdown-label">系统运维</span>
          <div class="fui-dropdown-content">
            <RouterLink v-if="can('system.read')" to="/license">许可证管理</RouterLink>
            <RouterLink v-if="can('user.read')" to="/admin/users">用户管理</RouterLink>
            <RouterLink v-if="can('system.read')" to="/system/settings">系统设置</RouterLink>
          </div>
        </div>

        <RouterLink v-if="can('package.read')" to="/templates" class="nav-item">下载中心</RouterLink>
      </nav>
      <div v-else></div>

      <div class="fui-brand">
        <h1 class="fui-sys-title">工业智能算法运行与管控平台</h1>
        <p class="fui-eyebrow">INDUSTRIAL ALGORITHM OPERATIONS CENTER</p>
      </div>

      <div class="fui-user-block">
        <template v-if="auth.securityEnabled && auth.user">
          <RouterLink class="fui-profile" to="/profile">
            <div class="fui-avatar-box">
              <img v-if="auth.user.avatar_url" :src="auth.user.avatar_url" class="fui-avatar-img" />
              <span v-else class="fui-avatar-text">{{ auth.avatarText }}</span>
            </div>
            <div class="fui-user-meta">
              <strong>{{ auth.user.display_name }}</strong>
              <span>{{ auth.user.roles?.[0] || 'User' }}</span>
            </div>
          </RouterLink>
          <button type="button" class="fui-btn-logout" @click="signOut">退出 ⏻</button>
        </template>
        <RouterLink v-else-if="auth.securityEnabled && !showLoginPage" class="fui-btn-login" to="/login">登录</RouterLink>
      </div>
    </header>

    <main class="fui-main-content">
      <RouterView />
    </main>
  </div>
</template>

<style>
body {
  margin: 0;
  background-color: #030a16;
  color: #a0cfff;
  font-family: "DingTalk JinBuTi", "Microsoft YaHei", sans-serif;
  overflow-x: auto;
}
</style>

<style scoped>
.fui-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  min-width: 780px;
  background-image:
    radial-gradient(circle at 50% 0%, #002244 0%, transparent 50%),
    linear-gradient(rgba(0, 243, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 243, 255, 0.03) 1px, transparent 1px);
  background-size: 100% 100%, 40px 40px, 40px 40px;
}
.fui-topbar {
  position: relative;
  min-height: 90px;
  height: auto;
  background: url('data:image/svg+xml;utf8,<svg preserveAspectRatio="none" viewBox="0 0 1920 80" xmlns="http://www.w3.org/2000/svg"><path d="M0,0 L1920,0 L1920,50 L1450,50 L1400,80 L520,80 L470,50 L0,50 Z" fill="rgba(2, 18, 38, 0.9)" stroke="%23005f8f" stroke-width="2"/></svg>') no-repeat center top;
  background-size: 100% 100%;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 20px;
  padding: 0 30px;
  z-index: 1000;
}

/* 导航基础样式 */
.fui-nav-menu {
  display: flex;
  gap: 12px;
  margin-top: 6px;
  margin-bottom: 15px;
  justify-self: start;
}

/* 下拉容器 */
.fui-dropdown {
  position: relative;
  display: inline-block;
}

.fui-dropdown-label, .nav-item {
  display: block;
  color: #a0cfff;
  text-decoration: none;
  font-size: 14px;
  font-weight: bold;
  padding: 6px 16px;
  border: 1px solid rgba(0, 243, 255, 0.3);
  background: rgba(0, 243, 255, 0.05);
  transition: all 0.3s;
  clip-path: polygon(8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%, 0 8px);
  cursor: pointer;
  white-space: nowrap;
}

/* 悬停与激活状态 */
.fui-dropdown:hover .fui-dropdown-label,
.nav-item:hover,
.nav-item.router-link-active {
  background: rgba(0, 243, 255, 0.2);
  border-color: #00f3ff;
  color: #00f3ff;
  box-shadow: 0 0 10px rgba(0, 243, 255, 0.3);
}

/* 下拉菜单主体 */
.fui-dropdown-content {
  display: none;
  position: absolute;
  top: 100%;
  left: 0;
  min-width: 140px;
  background: rgba(2, 18, 38, 0.95);
  border: 1px solid #005f8f;
  padding: 8px 0;
  z-index: 10;
  box-shadow: 0 8px 16px rgba(0,0,0,0.5);
  backdrop-filter: blur(10px);
}

.fui-dropdown:hover .fui-dropdown-content {
  display: block;
  animation: fadeIn 0.2s ease-out;
}

.fui-dropdown-content a {
  color: #a0cfff;
  padding: 10px 20px;
  text-decoration: none;
  display: block;
  font-size: 13px;
  transition: all 0.2s;
  border-left: 2px solid transparent; /* 预留一个边框位 */
}

/* 重点：悬停 (hover) 和 激活 (active) 状态统一 */
.fui-dropdown-content a:hover,
.fui-dropdown-content a.router-link-active {
  background: rgba(0, 243, 255, 0.1); /* 浅蓝色透明背景，拒绝纯白 */
  color: #00f3ff;
  padding-left: 25px; /* 侧滑动画 */
  border-left: 2px solid #00f3ff; /* 左侧加一条细细的发光线，更高级 */
  text-shadow: 0 0 8px rgba(0, 243, 255, 0.5);
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* 其他样式保持不变 */
.fui-brand { text-align: center; pointer-events: none; min-width: 240px; }
.fui-sys-title {
  margin: 0;
  font-size: 24px;
  font-weight: 900;
  color: #00f3ff;
  text-shadow: 0 0 15px rgba(0, 243, 255, 0.7);
  letter-spacing: 3px;
  white-space: nowrap;
}
.fui-eyebrow { margin: 2px 0 0; font-size: 10px; color: #a0cfff; letter-spacing: 0.2em; opacity: 0.8; white-space: nowrap; }
.fui-user-block { display: flex; align-items: center; gap: 20px; justify-self: end; margin-top: 6px; margin-bottom: 15px; }
.fui-profile { display: flex; align-items: center; gap: 12px; text-decoration: none; cursor: pointer; padding: 5px 10px; border-radius: 8px; transition: background 0.3s; }
.fui-profile:hover { background: rgba(255, 255, 255, 0.05); }
.fui-avatar-box { width: 36px; height: 36px; border-radius: 50%; border: 2px solid #00f3ff; overflow: hidden; display: flex; align-items: center; justify-content: center; background: #030a16; box-shadow: 0 0 10px rgba(0, 243, 255, 0.5); }
.fui-avatar-img { width: 100%; height: 100%; object-fit: cover; }
.fui-avatar-text { color: #00f3ff; font-weight: bold; }
.fui-user-meta strong { color: #fff; font-size: 14px; display: block; }
.fui-user-meta span { color: #00f3ff; font-size: 11px; opacity: 0.8; }
.fui-btn-logout { background: rgba(255, 68, 68, 0.1); border: 1px solid #ff4444; color: #ff4444; padding: 6px 14px; cursor: pointer; font-size: 13px; font-weight: bold; transition: 0.3s; clip-path: polygon(6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%, 0 6px); }
.fui-btn-logout:hover { background: #ff4444; color: #fff; box-shadow: 0 0 15px rgba(255, 68, 68, 0.5); }
.fui-btn-login { background: rgba(0, 243, 255, 0.1); border: 1px solid #00f3ff; color: #00f3ff; padding: 6px 20px; text-decoration: none; font-weight: bold; clip-path: polygon(6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%, 0 6px); transition: 0.3s; }
.fui-btn-login:hover { background: #00f3ff; color: #030a16; box-shadow: 0 0 20px rgba(0, 243, 255, 0.5); }
.fui-main-content { flex: 1; padding: 24px; margin: 0 auto; width: 100%; box-sizing: border-box; }

@media (max-width: 1024px) {
  .fui-sys-title { font-size: 20px; letter-spacing: 1px; }
  .fui-nav-menu { gap: 6px; }
  .fui-dropdown-label, .nav-item { padding: 4px 10px; font-size: 12px; }
}
</style>