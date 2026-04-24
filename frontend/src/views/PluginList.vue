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
  <div class="plugin-list-container">
    <!-- 头部区域 -->
    <header class="page-header">
      <div class="header-text">
        <span class="eyebrow">插件管理</span>
        <h2 class="page-title">插件管理</h2>
        <p class="page-subtitle">查看已登记的插件包、最新版本和版本记录。</p>
      </div>
      <button class="btn btn-primary" @click="loadPackages" :disabled="loading">
        <svg v-if="loading" class="spin-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
        <svg v-else class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
        {{ loading ? '刷新中...' : '刷新列表' }}
      </button>
    </header>

    <!-- 状态通知提示 -->
    <div v-if="error" class="alert alert-error">{{ error }}</div>

    <!-- 空状态 / 加载状态 -->
    <div v-if="loading && packages.length === 0" class="state-container">
      <div class="spinner"></div>
      <p>正在加载插件包数据...</p>
    </div>

    <div v-else-if="packages.length === 0" class="state-container empty">
      <div class="empty-icon">📦</div>
      <h3>暂无插件包</h3>
      <p>上传插件包并通过 manifest 校验后，这里会出现版本记录。</p>
    </div>

    <!-- 列表主体 -->
    <main v-else class="list-wrapper">
      <div class="list-meta">
        共 <span class="highlight">{{ packages.length }}</span> 个插件包，当前显示第 <span>{{ currentPage }}</span> 页
      </div>

      <div v-for="item in pagedPackages" :key="item.id" class="package-card" :class="{'is-expanded': versions[item.name]}">
        <!-- 卡片头部 (插件概览) -->
        <div class="card-body">
          <div class="pkg-main">
            <div class="pkg-avatar">{{ item.name.charAt(0).toUpperCase() }}</div>
            <div class="pkg-info">
              <div class="pkg-title-wrapper">
                <h3 class="pkg-display-name">{{ item.display_name || item.name }}</h3>
                <span class="badge">{{ item.status }}</span>
              </div>
              <p class="pkg-name">{{ item.name }}</p>
              <p class="pkg-desc">{{ item.description || '暂无描述信息' }}</p>
            </div>
          </div>

          <div class="pkg-stats">
            <div class="stat-item">
              <span class="stat-label">版本数</span>
              <span class="stat-value">{{ item.version_count }}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">最新版本</span>
              <span class="stat-value text-mono">{{ item.latest_version ?? '暂无' }}</span>
            </div>
          </div>

          <div class="pkg-actions">
            <button class="btn btn-outline" @click="toggleVersions(item.name)" :disabled="loadingVersions === item.name || deletingPackage === item.name">
              {{ versions[item.name] ? '收起版本' : loadingVersions === item.name ? '加载中...' : '版本管理' }}
            </button>
            <button class="btn btn-danger" @click="removePackage(item)" :disabled="deletingPackage === item.name || loadingVersions === item.name">
              {{ deletingPackage === item.name ? '删除中...' : '删除插件' }}
            </button>
          </div>
        </div>

        <!-- 展开的版本列表 (手风琴) -->
        <div v-if="versions[item.name]" class="version-panel">
          <h4 class="panel-title">版本运行与历史</h4>
          <div class="version-grid">
            <div v-for="version in versions[item.name]" :key="version.id" class="version-card">
              <div class="ver-header">
                <div class="ver-title">
                  <span class="ver-number">{{ version.version }}</span>
                  <span class="badge badge-light">{{ version.status }}</span>
                </div>
              </div>
              <div class="ver-meta">
                <div class="meta-row"><span class="meta-key">Digest:</span> <span class="meta-val text-mono">{{ version.digest?.substring(0, 16) || version.digest }}...</span></div>
                <div class="meta-row"><span class="meta-key">Path:</span> <span class="meta-val text-mono">{{ version.package_path }}</span></div>
              </div>

              <div class="ver-runner">
                <label class="input-label">Dry-run 入参 (JSON)</label>
                <textarea class="json-textarea" v-model="runInputs[version.id]" rows="3" spellcheck="false" placeholder='{"key": "value"}'></textarea>
                <button class="btn btn-primary btn-sm run-btn" @click="runVersion(item.name, version)" :disabled="runningVersion === `${item.name}@${version.version}`">
                  <svg class="icon-sm" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                  {{ runningVersion === `${item.name}@${version.version}` ? '执行中...' : '执行测试' }}
                </button>
                
                <div class="result-box" v-if="runResults[version.id]">
                  <div class="result-header">执行结果</div>
                  <pre class="result-code">{{ formatJson(runResults[version.id]) }}</pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 分页栏 -->
      <div class="pagination-bar" v-if="packages.length > PAGE_SIZE">
        <button class="btn btn-outline" @click="goToPage(currentPage - 1)" :disabled="currentPage <= 1">上一页</button>
        <span class="page-indicator">第 <strong>{{ currentPage }}</strong> / {{ totalPages }} 页</span>
        <button class="btn btn-outline" @click="goToPage(currentPage + 1)" :disabled="currentPage >= totalPages">下一页</button>
      </div>
    </main>
  </div>
</template>

<style scoped>
/* 全局容器变量与基础重置 */
.plugin-list-container {
  --primary: #12685f;
  --primary-hover: #0f5b53;
  --danger: #b42318;
  --danger-hover: #912018;
  --border: #d8e3df;
  --bg-light: #f8fbfa;
  --text-main: #1f2f2c;
  --text-muted: #5e6f6c;
  max-width: 1080px;
  margin: 0 auto;
  padding: 24px;
  font-family: system-ui, -apple-system, sans-serif;
  color: var(--text-main);
}

/* 头部排版 */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--border);
}
.eyebrow {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 1px;
}
.page-title {
  margin: 8px 0 4px;
  font-size: 28px;
  font-weight: 700;
}
.page-subtitle {
  margin: 0;
  font-size: 14px;
  color: var(--text-muted);
}

/* 通用按钮 */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  font-size: 14px;
  font-weight: 500;
  border-radius: 8px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-sm { padding: 6px 12px; font-size: 13px; }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-primary { background: var(--primary); color: #fff; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
.btn-primary:hover:not(:disabled) { background: var(--primary-hover); }
.btn-outline { background: #fff; border-color: #bacac5; color: #2f403d; }
.btn-outline:hover:not(:disabled) { background: var(--bg-light); border-color: #9db8b1; color: var(--primary); }
.btn-danger { background: #fff; border-color: #fca5a5; color: var(--danger); }
.btn-danger:hover:not(:disabled) { background: #fef3f2; border-color: #fda29b; color: var(--danger-hover); }

.icon, .icon-sm { width: 16px; height: 16px; }
.spin-icon { width: 16px; height: 16px; animation: spin 1s linear infinite; }
@keyframes spin { 100% { transform: rotate(360deg); } }

/* 提示与状态 */
.alert-error {
  padding: 12px 16px;
  background: #fef2f2;
  border-left: 4px solid var(--danger);
  color: #b91c1c;
  border-radius: 6px;
  margin-bottom: 24px;
  font-size: 14px;
}
.state-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 64px 0;
  color: var(--text-muted);
}
.empty-icon { font-size: 48px; margin-bottom: 16px; opacity: 0.8; }
.spinner {
  width: 32px; height: 32px;
  border: 3px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 16px;
}

/* 列表容器 */
.list-meta {
  font-size: 14px;
  color: var(--text-muted);
  margin-bottom: 16px;
}
.highlight { font-weight: 600; color: var(--text-main); }

/* 主卡片样式 */
.package-card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 12px;
  margin-bottom: 16px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.03);
  transition: border-color 0.2s, box-shadow 0.2s;
  overflow: hidden;
}
.package-card:hover { border-color: #9db8b1; box-shadow: 0 4px 10px rgba(15,42,37,0.08); }
.package-card.is-expanded { border-color: var(--primary); }

.card-body {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  flex-wrap: wrap;
  gap: 24px;
}

/* 卡片信息区 */
.pkg-main { display: flex; align-items: flex-start; gap: 16px; flex: 1; min-width: 300px; }
.pkg-avatar {
  width: 48px; height: 48px;
  background: linear-gradient(135deg, #eef8f6, #deeeea);
  color: var(--primary);
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-size: 20px; font-weight: 700; flex-shrink: 0;
}
.pkg-title-wrapper { display: flex; align-items: center; gap: 12px; }
.pkg-display-name { margin: 0; font-size: 18px; font-weight: 600; }
.badge { padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 500; background: #eef3f1; color: #41524f; }
.badge-light { background: #f3f7f6; color: #5e6f6c; }
.pkg-name { font-family: ui-monospace, monospace; font-size: 13px; color: var(--text-muted); margin: 4px 0; }
.pkg-desc { font-size: 14px; color: #41524f; margin: 8px 0 0; line-height: 1.5; }

/* 卡片指标区 */
.pkg-stats { display: flex; gap: 32px; }
.stat-item { display: flex; flex-direction: column; gap: 4px; }
.stat-label { font-size: 12px; color: var(--text-muted); text-transform: uppercase; }
.stat-value { font-size: 15px; font-weight: 600; color: var(--text-main); }
.text-mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }

/* 卡片操作区 */
.pkg-actions { display: flex; gap: 12px; }

/* 手风琴版本列表 */
.version-panel {
  background: var(--bg-light);
  border-top: 1px solid var(--border);
  padding: 24px;
}
.panel-title { margin: 0 0 16px 0; font-size: 15px; color: var(--text-main); }
.version-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px; }

.version-card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
}
.ver-header { margin-bottom: 12px; }
.ver-title { display: flex; align-items: center; justify-content: space-between; }
.ver-number { font-size: 16px; font-weight: 600; font-family: ui-monospace, monospace; }
.ver-meta { font-size: 12px; margin-bottom: 16px; }
.meta-row { margin-bottom: 4px; display: flex; }
.meta-key { color: var(--text-muted); width: 50px; flex-shrink: 0; }
.meta-val { color: var(--text-main); word-break: break-all; }

/* JSON 运行测试区 */
.ver-runner {
  border-top: 1px dashed #c7d6d1;
  padding-top: 16px;
}
.input-label { display: block; font-size: 12px; font-weight: 500; margin-bottom: 8px; color: #41524f; }
.json-textarea {
  width: 100%;
  padding: 8px;
  font-family: ui-monospace, monospace;
  font-size: 12px;
  border: 1px solid #bacac5;
  border-radius: 6px;
  resize: vertical;
  margin-bottom: 12px;
  background: #f8fbfa;
  box-sizing: border-box;
}
.json-textarea:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 2px rgba(18,104,95,0.12); }
.run-btn { width: 100%; justify-content: center; }

/* 执行结果反馈 */
.result-box { margin-top: 12px; border-radius: 6px; overflow: hidden; border: 1px solid #d8e3df; }
.result-header { background: #f3f7f6; padding: 6px 12px; font-size: 12px; font-weight: 600; color: #41524f; border-bottom: 1px solid #d8e3df; }
.result-code { margin: 0; padding: 12px; background: #1f2f2c; color: #f8fafc; font-size: 12px; font-family: ui-monospace, monospace; overflow-x: auto; max-height: 200px; }

/* 分页 */
.pagination-bar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 16px;
  margin-top: 24px;
}
.page-indicator { font-size: 14px; color: var(--text-muted); }
</style>
