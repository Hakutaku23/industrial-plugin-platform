<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter, RouterLink, RouterView } from 'vue-router'
import { useAuthStore } from './stores/auth' // 确保路径正确

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

// 判断是否显示登录页
const showLoginPage = computed(() => route.path === '/login')

// 权限校验函数
const can = (permission: string) => auth.can(permission)

// 退出登录逻辑
async function signOut() {
  await auth.signOut()
  if (auth.securityEnabled) {
    await router.replace('/login')
  }
}
</script>

<template>
  <div class="fui-shell">
    <header class="fui-topbar">
      <!-- 左侧导航区 -->
      <nav v-if="!showLoginPage" class="fui-nav-menu">
        <RouterLink v-if="can('package.read')" to="/">首页</RouterLink>
        <RouterLink v-if="can('package.read')" to="/packages/upload">插件上传</RouterLink>
        <RouterLink v-if="can('package.read')" to="/packages">插件管理</RouterLink>
        <RouterLink v-if="can('datasource.read')" to="/data-sources">数据源管理</RouterLink>
        <RouterLink v-if="can('instance.read')" to="/instances">实例管理</RouterLink>
        <RouterLink v-if="can('run.read')" to="/runs">运行记录</RouterLink>
        <RouterLink v-if="can('system.read')" to="/license">许可证管理</RouterLink>
        <RouterLink v-if="can('user.read')" to="/admin/users">用户管理</RouterLink>
      </nav>

      <!-- 中间品牌区 -->
      <div class="fui-brand">
        <h1 class="fui-sys-title">工业智能算法运行与管控平台</h1>
        <p class="fui-eyebrow">INDUSTRIAL ALGORITHM OPERATIONS CENTER</p>
      </div>

      <!-- 右侧用户区 -->
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
          <button type="button" class="fui-btn-logout" @click="signOut">
            退出 ⏻
          </button>
        </template>
        <RouterLink v-else-if="auth.securityEnabled" class="fui-btn-login" to="/login">
          登录
        </RouterLink>
      </div>
    </header>

    <main class="fui-main-content">
      <router-view />
    </main>
  </div>
</template>

<style>
/* 全局深色底色，防止滚动时出现白边 */
body {
  margin: 0;
  background-color: #030a16;
  color: #a0cfff;
  font-family: "DingTalk JinBuTi", "Microsoft YaHei", sans-serif;
  overflow-x: auto; /* 确保窄屏时出现滚动条，避免内容挤压重叠 */
}
</style>

<style scoped>
.fui-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  min-width: 780px; /* 防止顶部元素重叠的最小宽度，可根据实际内容调整 */
  background-image: 
    radial-gradient(circle at 50% 0%, #002244 0%, transparent 50%),
    linear-gradient(rgba(0, 243, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 243, 255, 0.03) 1px, transparent 1px);
  background-size: 100% 100%, 40px 40px, 40px 40px;
}

.fui-topbar {
  position: relative;
  /* 修改：移除固定高度，改为最小高度 + 自动撑开，使顶部栏高度随导航菜单换行自适应 */
  min-height: 90px;
  height: auto;
  background: url('data:image/svg+xml;utf8,<svg preserveAspectRatio="none" viewBox="0 0 1920 80" xmlns="http://www.w3.org/2000/svg"><path d="M0,0 L1920,0 L1920,50 L1450,50 L1400,80 L520,80 L470,50 L0,50 Z" fill="rgba(2, 18, 38, 0.9)" stroke="%23005f8f" stroke-width="2"/></svg>') no-repeat center top;
  background-size: 100% 100%;
  /* 使用grid布局，确保三个区域完全分离，中间标题绝对居中 */
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 20px;
  padding: 0 30px;
  z-index: 1000;
}

/* 左侧导航区 - 下移微调，避免与背景折线视觉冲突 */
.fui-nav-menu {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;      /* 允许折行以防万一 */
  margin-top: 6px;     /* 向下移动，避免与标题区域干涉，也符合背景裁切美感 */
  margin-bottom: 15px;
  justify-self: start;  /* 左对齐 */
}

.fui-nav-menu a {
  color: #a0cfff;
  text-decoration: none;
  font-size: 13px;
  font-weight: bold;
  padding: 6px 14px;
  border: 1px solid transparent;
  transition: all 0.3s;
  clip-path: polygon(8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%, 0 8px);
  white-space: nowrap;  /* 避免文字换行导致高度突变，若屏幕过窄会触发父级滚动 */
}

.fui-nav-menu a:hover,
.fui-nav-menu a.router-link-active {
  background: rgba(0, 243, 255, 0.15);
  border-color: #00f3ff;
  color: #00f3ff;
  box-shadow: inset 0 0 10px rgba(0, 243, 255, 0.3);
}

/* 品牌区 - 自然居中，不再绝对定位 */
.fui-brand {
  text-align: center;
  pointer-events: none;
  /* 保留最小宽度，避免内容挤压时过度换行 */
  min-width: 240px;
}

.fui-sys-title {
  margin: 0;
  font-size: 24px;
  font-weight: 900;
  color: #00f3ff;
  text-shadow: 0 0 15px rgba(0, 243, 255, 0.7);
  letter-spacing: 3px;
  white-space: nowrap;  /* 标题不换行，窄屏出现滚动条时保持可读 */
}

.fui-eyebrow {
  margin: 2px 0 0;
  font-size: 10px;
  color: #a0cfff;
  letter-spacing: 0.2em;
  opacity: 0.8;
  white-space: nowrap;
}

/* 右侧用户区 - 右对齐 */
.fui-user-block {
  display: flex;
  align-items: center;
  gap: 20px;
  justify-self: end;    /* grid内右对齐 */
  margin-top: 6px;      /* 轻微下移，与导航视觉平衡 */
  margin-bottom: 15px;
}

.fui-profile {
  display: flex;
  align-items: center;
  gap: 12px;
  text-decoration: none;
  cursor: pointer;
  padding: 5px 10px;
  border-radius: 8px;
  transition: background 0.3s;
}
.fui-profile:hover {
  background: rgba(255, 255, 255, 0.05);
}

.fui-avatar-box {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 2px solid #00f3ff;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #030a16;
  box-shadow: 0 0 10px rgba(0, 243, 255, 0.5);
}
.fui-avatar-img { width: 100%; height: 100%; object-fit: cover; }
.fui-avatar-text { color: #00f3ff; font-weight: bold; }

.fui-user-meta strong { color: #fff; font-size: 14px; display: block; }
.fui-user-meta span { color: #00f3ff; font-size: 11px; opacity: 0.8; }

.fui-btn-logout {
  background: rgba(255, 68, 68, 0.1);
  border: 1px solid #ff4444;
  color: #ff4444;
  padding: 6px 14px;
  cursor: pointer;
  font-size: 13px;
  font-weight: bold;
  transition: 0.3s;
  clip-path: polygon(6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%, 0 6px);
}
.fui-btn-logout:hover {
  background: #ff4444;
  color: #fff;
  box-shadow: 0 0 15px rgba(255, 68, 68, 0.5);
}

.fui-btn-login {
  background: rgba(0, 243, 255, 0.1);
  border: 1px solid #00f3ff;
  color: #00f3ff;
  padding: 6px 20px;
  text-decoration: none;
  font-weight: bold;
  clip-path: polygon(6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%, 0 6px);
  transition: 0.3s;
}
.fui-btn-login:hover {
  background: #00f3ff;
  color: #030a16;
  box-shadow: 0 0 20px rgba(0, 243, 255, 0.5);
}

.fui-main-content {
  flex: 1;
  padding: 24px;
  max-width: 1600px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
}

/* 响应式微调：当窗口宽度略低于最小宽度时，依赖全局滚动条，布局依然稳定 */
@media (max-width: 880px) {
  .fui-sys-title {
    font-size: 20px;
    letter-spacing: 1px;
  }
  .fui-eyebrow {
    font-size: 8px;
    letter-spacing: 0.1em;
  }
  .fui-nav-menu a {
    padding: 4px 10px;
    font-size: 12px;
  }
  .fui-topbar {
    gap: 12px;
    padding: 0 16px;
  }
}
</style>