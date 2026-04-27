<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  deletePackage,
  listPackages,
  listPackageVersions,
  runPackageVersion,
  type PluginPackageSummary,
  type PluginVersionRecord,
  type RunPluginResult,
} from '../api/packages'

const packages = ref<PluginPackageSummary[]>([])
const versions = ref<Record<string, PluginVersionRecord[]>>({})
const loading = ref(false)
const loadingVersions = ref('')
const runningVersion = ref('')
const deletingPackage = ref('')
const error = ref('')
const runInputs = ref<Record<number, string>>({})
const runResults = ref<Record<number, RunPluginResult>>({})

const visibleCount = ref(10)
const currentPage = ref(1)
const PAGE_SIZE = 10

async function loadPackages() {
  loading.value = true
  error.value = ''
  try {
    packages.value = await listPackages()
    currentPage.value = 1
  } catch (err) {
    error.value = err instanceof Error ? err.message : '插件包列表加载失败'
  } finally {
    loading.value = false
  }
}

async function toggleVersions(packageName: string) {
  if (versions.value[packageName]) {
    delete versions.value[packageName]
    versions.value = { ...versions.value }
    return
  }

  loadingVersions.value = packageName
  error.value = ''
  try {
    const loadedVersions = await listPackageVersions(packageName)
    versions.value = {
      ...versions.value,
      [packageName]: loadedVersions,
    }
    for (const version of loadedVersions) {
      runInputs.value[version.id] = runInputs.value[version.id] ?? '{}'
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '插件版本加载失败'
  } finally {
    loadingVersions.value = ''
  }
}

async function runVersion(packageName: string, version: PluginVersionRecord) {
  runningVersion.value = `${packageName}@${version.version}`
  error.value = ''
  try {
    const parsedInputs = JSON.parse(runInputs.value[version.id] || '{}')
    if (!parsedInputs || Array.isArray(parsedInputs) || typeof parsedInputs !== 'object') {
      throw new Error('输入 JSON 必须是对象')
    }
    const result = await runPackageVersion(packageName, version.version, parsedInputs)
    runResults.value = {
      ...runResults.value,
      [version.id]: result,
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '插件执行失败'
  } finally {
    runningVersion.value = ''
  }
}

async function removePackage(item: PluginPackageSummary) {
  const confirmed = window.confirm(`确认删除插件包 ${item.name} 吗？\n\n这会删除该插件的版本、实例、运行记录与本地存储目录。`)
  if (!confirmed) {
    return
  }

  deletingPackage.value = item.name
  error.value = ''
  try {
    await deletePackage(item.name)
    delete versions.value[item.name]
    versions.value = { ...versions.value }
    packages.value = packages.value.filter((pkg) => pkg.name !== item.name)
    if (currentPage.value > totalPages.value) {
      currentPage.value = totalPages.value
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '插件包删除失败'
  } finally {
    deletingPackage.value = ''
  }
}

const totalPages = computed(() => Math.max(1, Math.ceil(packages.value.length / PAGE_SIZE)))
const pagedPackages = computed(() => {
  const start = (currentPage.value - 1) * PAGE_SIZE
  return packages.value.slice(start, start + PAGE_SIZE)
})

function goToPage(page: number) {
  if (page < 1 || page > totalPages.value || page === currentPage.value) {
    return
  }
  currentPage.value = page
}

function formatJson(value: unknown) {
  return JSON.stringify(value, null, 2)
}

onMounted(loadPackages)
</script>

<template>
  <div class="tech-container">
    <div class="plugin-list-container">
      
      <!-- 头部区域 -->
      <header class="page-header">
        <div class="header-text">
          <span class="eyebrow">PLUGIN MANAGEMENT</span>
          <h2 class="page-title">插件管理</h2>
          <p class="page-subtitle">查看已登记的插件包、最新版本和版本记录</p>
        </div>
        <button class="tech-btn" @click="loadPackages" :disabled="loading">
          <svg v-if="loading" class="spin-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
          <svg v-else class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
          {{ loading ? 'SYSTEM REFRESHING...' : '刷新状态' }}
        </button>
      </header>

      <!-- 状态通知提示 -->
      <div v-if="error" class="alert alert-error">
        <span class="alert-icon">⚠</span> {{ error }}
      </div>

      <!-- 空状态 / 加载状态 -->
      <div v-if="loading && packages.length === 0" class="state-container">
        <div class="tech-spinner"></div>
        <p class="glitch-text">DATA LOADING...</p>
      </div>

      <div v-else-if="packages.length === 0" class="state-container empty cyber-panel">
        <div class="empty-icon">📦</div>
        <h3>暂无插件数据</h3>
        <p>系统环境尚未检测到已安装的插件包</p>
      </div>

      <!-- 列表主体 -->
      <main v-else class="list-wrapper">
        <div class="list-meta">
          系统共检索到 <span class="highlight">{{ packages.length }}</span> 个插件节点 | 页面 [{{ currentPage }} / {{ totalPages }}]
        </div>

        <div v-for="item in pagedPackages" :key="item.id" class="package-card cyber-panel" :class="{'is-expanded': versions[item.name]}">
          <!-- 科技感角标 -->
          <div class="corner corner-tl"></div>
          <div class="corner corner-br"></div>

          <!-- 卡片头部 (插件概览) -->
          <div class="card-body">
            <div class="pkg-main">
              <div class="pkg-avatar">{{ item.name.charAt(0).toUpperCase() }}</div>
              <div class="pkg-info">
                <div class="pkg-title-wrapper">
                  <h3 class="pkg-display-name">{{ item.display_name || item.name }}</h3>
                  <span class="tech-badge" :class="item.status === 'ACTIVE' ? 'badge-success' : ''">{{ item.status }}</span>
                </div>
                <p class="pkg-name">ID: {{ item.name }}</p>
                <p class="pkg-desc">{{ item.description || 'No description available in current manifest.' }}</p>
              </div>
            </div>

            <div class="pkg-stats">
              <div class="stat-item">
                <span class="stat-label">版本总数</span>
                <span class="stat-value">{{ item.version_count }}</span>
              </div>
              <div class="stat-item">
                <span class="stat-label">最新节点</span>
                <span class="stat-value text-cyan">{{ item.latest_version ?? 'NULL' }}</span>
              </div>
            </div>

            <div class="pkg-actions">
              <button class="tech-btn btn-ghost" @click="toggleVersions(item.name)" :disabled="loadingVersions === item.name || deletingPackage === item.name">
                {{ versions[item.name] ? '收起面板' : loadingVersions === item.name ? 'LOADING...' : '进入管控' }}
              </button>
              <button class="tech-btn btn-danger" @click="removePackage(item)" :disabled="deletingPackage === item.name || loadingVersions === item.name">
                {{ deletingPackage === item.name ? 'PURGING...' : '销毁插件' }}
              </button>
            </div>
          </div>

          <!-- 展开的版本列表 (下级科技面板) -->
          <div v-if="versions[item.name]" class="version-panel">
            <h4 class="panel-title">运行频率与快照监控</h4>
            <div class="version-grid">
              <div v-for="version in versions[item.name]" :key="version.id" class="version-card">
                <div class="ver-header">
                  <div class="ver-title">
                    <span class="ver-number">v {{ version.version }}</span>
                    <span class="tech-badge badge-ghost">{{ version.status }}</span>
                  </div>
                </div>
                <div class="ver-meta">
                  <div class="meta-row">
                    <span class="meta-key">Digest</span> 
                    <span class="meta-val text-cyan">{{ version.digest?.substring(0, 16) || version.digest }}...</span>
                  </div>
                  <div class="meta-row">
                    <span class="meta-key">Path</span> 
                    <span class="meta-val">{{ version.package_path }}</span>
                  </div>
                </div>

                <div class="ver-runner">
                  <label class="input-label">执行入参 (Dry-run JSON)</label>
                  <textarea class="tech-textarea" v-model="runInputs[version.id]" rows="3" spellcheck="false" placeholder='{"params": "value"}'></textarea>
                  <button class="tech-btn btn-block" @click="runVersion(item.name, version)" :disabled="runningVersion === `${item.name}@${version.version}`">
                    <svg class="icon-sm" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                    {{ runningVersion === `${item.name}@${version.version}` ? 'EXECUTING...' : 'INITIATE DRY-RUN' }}
                  </button>
                  
                  <div class="result-box" v-if="runResults[version.id]">
                    <div class="result-header">>>> Terminal Output</div>
                    <pre class="result-code">{{ formatJson(runResults[version.id]) }}</pre>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 分页栏 -->
        <div class="pagination-bar" v-if="packages.length > PAGE_SIZE">
          <button class="tech-btn btn-icon" @click="goToPage(currentPage - 1)" :disabled="currentPage <= 1">&lt; PREV</button>
          <span class="page-indicator"><span class="text-cyan">{{ currentPage }}</span> / {{ totalPages }}</span>
          <button class="tech-btn btn-icon" @click="goToPage(currentPage + 1)" :disabled="currentPage >= totalPages">NEXT &gt;</button>
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
/* 科技感主题变量 */
.tech-container {
  --bg-deep: #020813;
  --panel-bg: rgba(7, 18, 36, 0.7);
  --panel-border: #14355a;
  --cyan-main: #00e5ff;
  --cyan-hover: #00b8cc;
  --cyan-glow: rgba(0, 229, 255, 0.2);
  --text-primary: #e2f1ff;
  --text-secondary: #6b8fae;
  --danger-main: #ff4d4f;
  --danger-glow: rgba(255, 77, 79, 0.2);
  --success-main: #00ff88;
  
  min-height: 100vh;
  /* 科技感网格背景 */
  background-color: var(--bg-deep);
  background-image: 
    linear-gradient(rgba(0, 229, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 229, 255, 0.03) 1px, transparent 1px);
  background-size: 20px 20px;
  background-position: center top;
  padding: 30px;
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  color: var(--text-primary);
}

.plugin-list-container {
  max-width: 1200px;
  margin: 0 auto;
}

/* 通用字体修正 */
.text-cyan { color: var(--cyan-main); font-family: ui-monospace, monospace; }

/* 头部样式 */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
  padding-bottom: 15px;
  border-bottom: 1px solid var(--panel-border);
  position: relative;
}
.page-header::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 0;
  width: 100px;
  height: 2px;
  background: var(--cyan-main);
  box-shadow: 0 0 10px var(--cyan-main);
}
.eyebrow {
  font-size: 12px;
  font-weight: 700;
  color: var(--cyan-main);
  letter-spacing: 2px;
}
.page-title {
  margin: 8px 0 4px;
  font-size: 24px;
  font-weight: bold;
  text-shadow: 0 0 10px rgba(0, 229, 255, 0.3);
}
.page-subtitle {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
}

/* 科技感按钮 */
.tech-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 20px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 1px;
  color: var(--cyan-main);
  background: rgba(0, 229, 255, 0.05);
  border: 1px solid var(--cyan-main);
  cursor: pointer;
  transition: all 0.3s ease;
  border-radius: 2px;
  text-transform: uppercase;
}
.tech-btn:hover:not(:disabled) {
  background: var(--cyan-hover);
  color: #000;
  box-shadow: 0 0 15px var(--cyan-glow);
}
.tech-btn:disabled {
  border-color: var(--text-secondary);
  color: var(--text-secondary);
  background: transparent;
  cursor: not-allowed;
}

/* 按钮变体 */
.btn-ghost { border-color: var(--panel-border); color: var(--text-primary); }
.btn-ghost:hover:not(:disabled) { border-color: var(--cyan-main); color: var(--cyan-main); background: transparent; box-shadow: inset 0 0 10px var(--cyan-glow); }
.btn-danger { border-color: var(--danger-main); color: var(--danger-main); background: rgba(255, 77, 79, 0.05); }
.btn-danger:hover:not(:disabled) { background: var(--danger-main); color: #fff; box-shadow: 0 0 15px var(--danger-glow); }
.btn-block { width: 100%; margin-top: 10px; }
.btn-icon { padding: 6px 12px; }

/* 图标 */
.icon, .icon-sm { width: 16px; height: 16px; }
.spin-icon { width: 16px; height: 16px; animation: spin 1s linear infinite; }
@keyframes spin { 100% { transform: rotate(360deg); } }

/* HUD 面板基础样式 */
.cyber-panel {
  position: relative;
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  backdrop-filter: blur(4px);
}
/* HUD 角标装饰 */
.corner { position: absolute; width: 12px; height: 12px; }
.corner-tl { top: -1px; left: -1px; border-top: 2px solid var(--cyan-main); border-left: 2px solid var(--cyan-main); }
.corner-br { bottom: -1px; right: -1px; border-bottom: 2px solid var(--cyan-main); border-right: 2px solid var(--cyan-main); }

/* 提示与状态 */
.alert-error {
  padding: 12px 16px;
  background: rgba(255, 77, 79, 0.1);
  border-left: 3px solid var(--danger-main);
  color: var(--danger-main);
  margin-bottom: 24px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.state-container {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 80px 0; color: var(--text-secondary);
}
.tech-spinner {
  width: 40px; height: 40px;
  border: 2px solid var(--panel-border);
  border-top-color: var(--cyan-main);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 20px;
  box-shadow: 0 0 15px var(--cyan-glow);
}
.empty h3 { margin: 10px 0; color: var(--text-primary); }

/* 列表容器 */
.list-meta {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 16px;
  font-family: ui-monospace, monospace;
}
.highlight { color: var(--cyan-main); font-weight: bold; }

/* 主卡片样式 */
.package-card {
  margin-bottom: 20px;
  transition: box-shadow 0.3s, border-color 0.3s;
}
.package-card:hover { border-color: #245281; }
.package-card.is-expanded { border-color: var(--cyan-main); box-shadow: 0 0 20px rgba(0, 229, 255, 0.05); }

.card-body {
  display: flex; align-items: center; justify-content: space-between;
  padding: 24px; flex-wrap: wrap; gap: 24px;
}

/* 卡片信息区 */
.pkg-main { display: flex; align-items: center; gap: 20px; flex: 1; min-width: 300px; }
.pkg-avatar {
  width: 50px; height: 50px;
  background: rgba(0, 229, 255, 0.1);
  border: 1px solid var(--cyan-main);
  color: var(--cyan-main);
  display: flex; align-items: center; justify-content: center;
  font-size: 22px; font-weight: bold; font-family: ui-monospace, monospace;
  box-shadow: inset 0 0 10px var(--cyan-glow);
}
.pkg-title-wrapper { display: flex; align-items: center; gap: 12px; }
.pkg-display-name { margin: 0; font-size: 16px; font-weight: 600; letter-spacing: 1px; }

/* 标签 Badge */
.tech-badge {
  padding: 2px 8px; font-size: 11px; font-family: ui-monospace, monospace;
  border: 1px solid var(--cyan-main); color: var(--cyan-main); background: rgba(0, 229, 255, 0.1);
}
.badge-success { border-color: var(--success-main); color: var(--success-main); background: rgba(0, 255, 136, 0.1); }
.badge-ghost { border-color: var(--text-secondary); color: var(--text-secondary); background: transparent; }

.pkg-name { font-family: ui-monospace, monospace; font-size: 12px; color: var(--text-secondary); margin: 6px 0; }
.pkg-desc { font-size: 13px; color: #8faac2; margin: 8px 0 0; }

/* 卡片指标区 */
.pkg-stats { display: flex; gap: 40px; border-left: 1px solid var(--panel-border); padding-left: 40px; }
.stat-item { display: flex; flex-direction: column; gap: 6px; }
.stat-label { font-size: 12px; color: var(--text-secondary); font-family: ui-monospace, monospace; }
.stat-value { font-size: 16px; font-weight: bold; font-family: ui-monospace, monospace; }

/* 卡片操作区 */
.pkg-actions { display: flex; gap: 12px; }

/* 版本面板 (展开区域) */
.version-panel {
  background: rgba(0, 0, 0, 0.3);
  border-top: 1px solid var(--panel-border);
  padding: 24px;
}
.panel-title { margin: 0 0 20px 0; font-size: 14px; color: var(--cyan-main); font-weight: normal; border-left: 3px solid var(--cyan-main); padding-left: 8px; }
.version-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 20px; }

.version-card {
  background: rgba(10, 25, 45, 0.5);
  border: 1px solid #1c3d5a;
  padding: 16px;
  position: relative;
}
.version-card::before { content:''; position: absolute; top: 0; left: 0; width: 100%; height: 2px; background: #1c3d5a; }
.version-card:hover::before { background: var(--cyan-main); }

.ver-header { margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px dashed #1c3d5a; }
.ver-title { display: flex; align-items: center; justify-content: space-between; }
.ver-number { font-size: 15px; font-weight: bold; font-family: ui-monospace, monospace; color: #fff; }
.ver-meta { font-size: 12px; margin-bottom: 16px; font-family: ui-monospace, monospace; }
.meta-row { margin-bottom: 8px; display: flex; line-height: 1.4; }
.meta-key { color: var(--text-secondary); width: 60px; flex-shrink: 0; }
.meta-val { color: #a1c3e4; word-break: break-all; }

/* JSON 运行测试区 (类似终端) */
.ver-runner { margin-top: 16px; }
.input-label { display: block; font-size: 11px; color: var(--text-secondary); margin-bottom: 8px; font-family: ui-monospace, monospace; text-transform: uppercase; }
.tech-textarea {
  width: 100%; padding: 10px;
  font-family: ui-monospace, monospace; font-size: 12px;
  background: #02060c; border: 1px solid #1c3d5a; color: var(--cyan-main);
  resize: vertical; margin-bottom: 12px; outline: none; box-sizing: border-box;
}
.tech-textarea:focus { border-color: var(--cyan-main); box-shadow: inset 0 0 10px rgba(0, 229, 255, 0.1); }

/* 执行结果反馈 */
.result-box { margin-top: 16px; border: 1px solid var(--panel-border); background: #010408; }
.result-header { background: rgba(0, 229, 255, 0.1); padding: 6px 12px; font-size: 11px; color: var(--cyan-main); font-family: ui-monospace, monospace; border-bottom: 1px solid var(--panel-border); }
.result-code { margin: 0; padding: 12px; color: var(--success-main); font-size: 12px; font-family: ui-monospace, monospace; overflow-x: auto; max-height: 200px; }

/* 分页 */
.pagination-bar {
  display: flex; align-items: center; justify-content: flex-end; gap: 16px; margin-top: 30px;
}
.page-indicator { font-size: 13px; color: var(--text-secondary); font-family: ui-monospace, monospace; }

/* 自定义滚动条适配暗黑模式 */
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: var(--bg-deep); }
::-webkit-scrollbar-thumb { background: #1c3d5a; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: var(--cyan-main); }
</style>