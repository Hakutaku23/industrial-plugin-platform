<template>
  <main class="industrial-shell">
    <header class="topbar">
      <div class="brand">
        <p class="eyebrow">Industrial Algorithm Operations Center</p>
        <h1 class="sys-title">工业智能算法运行与管控平台</h1>
      </div>
      <nav v-if="!showLoginPage" class="nav-menu">
        <RouterLink v-if="can('package.read')" to="/">首页</RouterLink>
        <RouterLink v-if="can('package.read')" to="/packages/upload">插件上传</RouterLink>
        <RouterLink v-if="can('package.read')" to="/packages">插件管理</RouterLink>
        <RouterLink v-if="can('datasource.read')" to="/data-sources">数据源管理</RouterLink>
        <RouterLink v-if="can('instance.read')" to="/instances">实例管理</RouterLink>
        <RouterLink v-if="can('run.read')" to="/runs">运行记录</RouterLink>
        <RouterLink v-if="can('system.read')" to="/system/observability">系统观测</RouterLink>
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

<style scoped>
.industrial-shell {
  min-height: 100vh;
  font-family: Inter, "Microsoft YaHei", "PingFang SC", system-ui, -apple-system, "Segoe UI", sans-serif;
  display: flex;
  flex-direction: column;
}

.topbar {
  background: rgba(255, 255, 255, 0.95); /* 微透明，为玻璃效应当底 */
  backdrop-filter: blur(10px); /* 增加毛玻璃高级感 */
  color: #172126;
  border-bottom: none; /* 去掉生硬的灰线 */
  box-shadow: 0 2px 20px rgba(18, 104, 95, 0.08); /* 换成带一点点品牌青色的柔和阴影 */
  padding: 12px 24px;
  min-height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  position: sticky;
  top: 0;
  z-index: 100;
}

.brand { display: flex; flex-direction: column; justify-content: center; min-width: 260px; }
.eyebrow { margin: 0; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: #5e6f6c; font-weight: 700; }
.sys-title { margin: 2px 0 0; font-size: 18px; font-weight: 800; letter-spacing: 0.2px; color: #12211f; } /* 加深标题颜色 */

.nav-menu { display: flex; gap: 8px; height: 100%; align-items: center; flex-wrap: wrap; }
.nav-menu a, .secondary-link { color: #4a5c59; text-decoration: none; font-size: 14px; font-weight: 600; padding: 8px 14px; border-radius: 8px; transition: all 0.2s ease; }
.nav-menu a:hover, .secondary-link:hover { background-color: #f0f5f4; color: #12685f; }
/* 去掉原本生硬的边框，改用纯净的底色和加深字体 */
.nav-menu a.router-link-active { background-color: #e4efe9; color: #0b4d46; border: none; font-weight: 700;} 

.user-block { margin-left: auto; display: flex; align-items: center; gap: 12px; }
.profile-entry { display: inline-flex; align-items: center; gap: 10px; padding: 6px 10px; border-radius: 12px; color: inherit; text-decoration: none; transition: background-color 0.2s ease; }
.profile-entry:hover { background-color: #f0f5f4; }
.user-meta { display: grid; gap: 2px; text-align: left; }
.user-meta strong { font-size: 14px; color: #1f2f2c; }
.user-meta span { font-size: 12px; color: #5e6f6c; }
.avatar-fallback, .avatar-image-wrap { width: 36px; height: 36px; border-radius: 999px; display: inline-flex; align-items: center; justify-content: center; overflow: hidden; background: #12685f; color: #ffffff; font-weight: 700; box-shadow: 0 2px 8px rgba(18,104,95,0.2); }
.avatar-image { width: 100%; height: 100%; object-fit: cover; }
.main-content { flex: 1; padding: 24px 32px 32px; max-width: 1440px; margin: 0 auto; width: 100%; box-sizing: border-box; }
.secondary-button { min-height: 36px; padding: 0 14px; border-radius: 8px; border: 1px solid #d0deda; background: #ffffff; color: #2f403d; cursor: pointer; font-weight: 600; transition: all 0.2s ease;}
.secondary-button:hover { background: #f0f5f4; border-color: #bacac5; }
@media (max-width: 1100px) {
  .topbar { align-items: flex-start; padding-top: 12px; padding-bottom: 12px; }
  .brand { min-width: auto; }
}
</style>