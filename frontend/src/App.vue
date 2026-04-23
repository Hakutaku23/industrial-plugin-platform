<template>
  <main class="industrial-shell">
    <header class="topbar">
      <div class="brand">
        <p class="eyebrow">Industrial Plugin Platform</p>
        <h1 class="sys-title">工业算法插件管理平台</h1>
      </div>
      <nav v-if="!showLoginPage" class="nav-menu">
        <RouterLink v-if="can('package.read')" to="/">上传插件</RouterLink>
        <RouterLink v-if="can('package.read')" to="/packages">插件列表</RouterLink>
        <RouterLink v-if="can('datasource.read')" to="/data-sources">数据源</RouterLink>
        <RouterLink v-if="can('instance.read')" to="/instances">实例管理</RouterLink>
        <RouterLink v-if="can('run.read')" to="/runs">运行状态</RouterLink>
        <RouterLink v-if="can('system.read')" to="/license">许可证管理</RouterLink>
        <RouterLink v-if="can('user.read')" to="/admin/users">用户权限</RouterLink>
      </nav>
      <div class="user-block">
        <template v-if="auth.securityEnabled && auth.user">
          <RouterLink class="profile-entry" to="/profile">
            <span v-if="auth.user.avatar_url" class="avatar-image-wrap">
              <img :src="auth.user.avatar_url" alt="avatar" class="avatar-image" />
            </span>
            <span v-else class="avatar-fallback">{{ auth.avatarText }}</span>
            <div class="user-meta">
              <strong>{{ auth.user.display_name }}</strong>
              <span>{{ auth.user.roles.join(', ') }}</span>
            </div>
          </RouterLink>
          <button type="button" class="secondary-button" @click="signOut">退出</button>
        </template>
        <RouterLink v-else-if="auth.securityEnabled" class="secondary-link" to="/login">登录</RouterLink>
      </div>
    </header>

    <div class="main-content">
      <RouterView />
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed } from 'vue'
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
</script>

<style>
body {
  margin: 0;
  padding: 0;
  background-color: #f1f5f9;
}
</style>

<style scoped>
.industrial-shell { min-height: 100vh; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; display: flex; flex-direction: column; }
.topbar { background-color: #0f172a; color: #ffffff; padding: 0 24px; min-height: 64px; display: flex; align-items: center; justify-content: space-between; gap: 16px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06); position: sticky; top: 0; z-index: 100; }
.brand { display: flex; flex-direction: column; justify-content: center; }
.eyebrow { margin: 0; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: #94a3b8; font-weight: 600; }
.sys-title { margin: 2px 0 0; font-size: 18px; font-weight: 600; letter-spacing: 0.5px; color: #f8fafc; }
.nav-menu { display: flex; gap: 8px; height: 100%; align-items: center; flex-wrap: wrap; }
.nav-menu a, .secondary-link { color: #cbd5e1; text-decoration: none; font-size: 14px; font-weight: 500; padding: 8px 16px; border-radius: 6px; transition: all 0.2s ease; }
.nav-menu a:hover, .secondary-link:hover { background-color: #1e293b; color: #ffffff; }
.nav-menu a.router-link-active { background-color: #2563eb; color: #ffffff; box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05); }
.user-block { margin-left: auto; display: flex; align-items: center; gap: 12px; }
.profile-entry { display: inline-flex; align-items: center; gap: 10px; padding: 6px 10px; border-radius: 12px; color: inherit; text-decoration: none; transition: background-color 0.2s ease; }
.profile-entry:hover { background-color: rgba(255, 255, 255, 0.08); }
.user-meta { display: grid; gap: 2px; text-align: left; }
.user-meta strong { font-size: 14px; color: #ffffff; }
.user-meta span { font-size: 12px; color: #94a3b8; }
.avatar-fallback, .avatar-image-wrap { width: 36px; height: 36px; border-radius: 999px; display: inline-flex; align-items: center; justify-content: center; overflow: hidden; background: #2563eb; color: #ffffff; font-weight: 700; }
.avatar-image { width: 100%; height: 100%; object-fit: cover; }
.main-content { flex: 1; padding: 32px; max-width: 1440px; margin: 0 auto; width: 100%; box-sizing: border-box; }
.secondary-button { min-height: 36px; padding: 0 14px; border-radius: 8px; border: 1px solid #334155; background: #111827; color: #ffffff; cursor: pointer; }
</style>
