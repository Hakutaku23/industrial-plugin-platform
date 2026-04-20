<template>
  <main class="industrial-shell">
    <!-- 顶部导航栏 -->
    <header class="topbar">
      <div class="brand">
        <p class="eyebrow">Industrial Plugin Platform</p>
        <h1 class="sys-title">工业算法插件管理平台</h1>
      </div>
      <nav class="nav-menu">
        <RouterLink to="/">上传插件</RouterLink>
        <RouterLink to="/packages">插件列表</RouterLink>
        <RouterLink to="/data-sources">数据源</RouterLink>
        <RouterLink to="/instances">实例管理</RouterLink>
        <RouterLink to="/runs">运行状态</RouterLink>
      </nav>
    </header>

    <!-- 路由视图容器 (各个子页面在这里渲染) -->
    <div class="main-content">
      <RouterView />
    </div>
  </main>
</template>

<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
</script>

<style>
/* 全局重置，确保没有默认的边距干扰 */
body {
  margin: 0;
  padding: 0;
  background-color: #f1f5f9; /* 整体背景色：沉稳的浅灰蓝 */
}
</style>

<style scoped>
/* 系统外壳 */
.industrial-shell {
  min-height: 100vh;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  display: flex;
  flex-direction: column;
}

/* 顶部导航栏 (深色工业风) */
.topbar {
  background-color: #0f172a; /* 深岩灰 */
  color: #ffffff;
  padding: 0 32px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
  position: sticky;
  top: 0;
  z-index: 100;
}

/* 左侧品牌区 */
.brand {
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.eyebrow {
  margin: 0;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #94a3b8;
  font-weight: 600;
}

.sys-title {
  margin: 2px 0 0;
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.5px;
  color: #f8fafc;
}

/* 右侧导航菜单 */
.nav-menu {
  display: flex;
  gap: 8px;
  height: 100%;
  align-items: center;
}

.nav-menu a {
  color: #cbd5e1;
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  padding: 8px 16px;
  border-radius: 6px;
  transition: all 0.2s ease;
}

/* 鼠标悬浮状态 */
.nav-menu a:hover {
  background-color: #1e293b;
  color: #ffffff;
}

/* 当前所在页面的激活状态 (企业蓝) */
.nav-menu a.router-link-active {
  background-color: #2563eb;
  color: #ffffff;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

/* 主内容区域 */
.main-content {
  flex: 1;
  padding: 32px;
  max-width: 1440px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
}
</style>