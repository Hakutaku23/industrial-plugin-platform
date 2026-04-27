<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { listTemplates, type TemplateItem } from '../api/templates'

const templates = ref<TemplateItem[]>([])
const loading = ref(false)
const error = ref('')
const activeCategory = ref<'all' | 'plugin' | 'model'>('all')

const filtered = computed(() => {
  if (activeCategory.value === 'all') return templates.value
  return templates.value.filter((item) => item.category === activeCategory.value)
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    templates.value = await listTemplates()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '模板清单加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="template-page">
    <section class="panel">
      <div class="header-row">
        <div>
          <p class="eyebrow">TEMPLATE CENTER</p>
          <h2>模板中心</h2>
          <p class="desc">集中下载插件包、模型包和数据源示例模板。后续新增模板统一在此维护。</p>
        </div>
        <button class="btn ghost" :disabled="loading" @click="load">刷新</button>
      </div>

      <div class="tabs">
        <button :class="{ active: activeCategory === 'all' }" @click="activeCategory = 'all'">全部</button>
        <button :class="{ active: activeCategory === 'plugin' }" @click="activeCategory = 'plugin'">插件模板</button>
        <button :class="{ active: activeCategory === 'model' }" @click="activeCategory = 'model'">模型模板</button>
      </div>

      <div v-if="error" class="error">{{ error }}</div>
      <div class="template-grid">
        <article v-for="item in filtered" :key="item.name" class="template-card">
          <span class="category">{{ item.category }}</span>
          <h3>{{ item.title }}</h3>
          <p>{{ item.description }}</p>
          <a class="download" :href="item.download_url">下载模板</a>
        </article>
      </div>
    </section>
  </div>
</template>

<style scoped>
.template-page { min-height: 100vh; padding: 34px; color: #d9f7ff; background: #030a16; }
.panel { max-width: 1280px; margin: 0 auto; padding: 30px; background: rgba(2,18,38,.78); border: 1px solid rgba(0,243,255,.28); }
.header-row { display: flex; justify-content: space-between; gap: 18px; align-items: center; }
.eyebrow { color: #00f3ff; letter-spacing: 3px; font-size: 11px; margin: 0 0 8px; }
h2 { margin: 0 0 8px; color: #fff; }
.desc { margin: 0; color: rgba(217,247,255,.65); }
.btn, .tabs button, .download { border: 1px solid rgba(0,243,255,.45); background: rgba(0,243,255,.06); color: #00f3ff; padding: 9px 16px; cursor: pointer; font-weight: 800; text-decoration: none; }
.tabs { margin: 24px 0; display: flex; gap: 12px; }
.tabs button.active { background: #00f3ff; color: #001018; }
.error { color: #ff7890; border: 1px solid rgba(255,83,112,.45); padding: 12px; margin-bottom: 18px; }
.template-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; }
.template-card { padding: 20px; background: rgba(1,10,18,.72); border: 1px solid rgba(0,243,255,.22); display: grid; gap: 12px; }
.template-card h3 { margin: 0; color: #fff; }
.template-card p { margin: 0; color: rgba(217,247,255,.65); line-height: 1.6; }
.category { width: fit-content; color: #00f3ff; border: 1px solid rgba(0,243,255,.4); padding: 2px 8px; font-size: 12px; }
.download { width: fit-content; }
@media (max-width: 980px) { .template-grid { grid-template-columns: 1fr; } .header-row { flex-direction: column; align-items: flex-start; } }
</style>
