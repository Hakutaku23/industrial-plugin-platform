<template>
  <main class="shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">Industrial Plugin Platform</p>
        <h1>插件包管理</h1>
      </div>
      <nav>
        <RouterLink to="/">上传</RouterLink>
        <RouterLink to="/packages">列表</RouterLink>
        <RouterLink to="/data-sources">数据源</RouterLink>
        <RouterLink to="/instances">实例</RouterLink>
        <RouterLink to="/runs">运行</RouterLink>
      </nav>
    </header>
    <RouterView />
  </main>
</template>
