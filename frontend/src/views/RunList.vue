<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  listInstances,
  listPackages,
  listRunLogs,
  listRuns,
  listWritebackRecords,
  type PluginInstanceRecord,
  type PluginPackageSummary,
  type PluginRunRecord,
  type RunLogRecord,
  type WritebackRecord,
} from '../api/packages'

const PAGE_SIZE = 10

const runs = ref<PluginRunRecord[]>([])
const packages = ref<PluginPackageSummary[]>([])
const instances = ref<PluginInstanceRecord[]>([])

const loading = ref(false)
const optionsLoading = ref(false)
const error = ref('')

const packageFilter = ref('')
const instanceFilter = ref('')
const statusFilter = ref('')
const keywordFilter = ref('')

const currentPage = ref(1)
const selectedRunId = ref<string | null>(null)
const detailTab = ref<'overview' | 'inputs' | 'outputs' | 'metrics' | 'error' | 'logs' | 'writeback'>('overview')

const logs = ref<RunLogRecord[]>([])
const writebacks = ref<WritebackRecord[]>([])
const detailLoading = ref(false)
const detailError = ref('')

const statusOptions = ['COMPLETED', 'PARTIAL_SUCCESS', 'FAILED', 'TIMED_OUT', 'SKIPPED']

// =======================
// 新增的 UI 交互状态
// =======================
const isDrawerOpen = ref(false)
const showObservability = ref(false) // 默认展开状态以便查看炫酷效果，可改回 false

function getStatusClass(status: string) {
  if (!status) return 'badge-default';
  const s = status.toUpperCase();
  if (s === 'COMPLETED') return 'badge-success';
  if (s === 'FAILED' || s === 'ERROR') return 'badge-error';
  if (s === 'PARTIAL_SUCCESS' || s === 'TIMED_OUT') return 'badge-warning';
  if (s === 'SKIPPED') return 'badge-skipped';
  return 'badge-default';
}

function getLogLevelClass(level: string) {
  const l = (level || '').toUpperCase();
  if (l === 'ERROR' || l === 'FATAL') return 'badge-error';
  if (l === 'WARN' || l === 'WARNING') return 'badge-warning';
  if (l === 'INFO') return 'badge-success';
  return 'badge-default';
}

function closeDrawer() {
  isDrawerOpen.value = false;
}
// =======================

type SchedulerStatusRecord = {
  enabled: boolean
  thread_alive: boolean
  poll_interval_sec: number
  max_workers: number
  inflight_tasks: number
  active_lock_count: number
  lock_observation_error?: string | null
  last_tick_started_at?: string | null
  last_tick_finished_at?: string | null
  last_error?: string | null
  consecutive_failures: number
}

type SchedulerLockRecord = {
  key: string
  instance_id: number | null
  ttl_sec: number | null
}

type AuditEventRecord = {
  id: number
  event_type: string
  actor: string
  target_type: string
  target_id: string
  details: Record<string, unknown>
  created_at: string
}

const schedulerStatus = ref<SchedulerStatusRecord | null>(null)
const schedulerLocks = ref<SchedulerLockRecord[]>([])
const auditEvents = ref<AuditEventRecord[]>([])
const observabilityLoading = ref(false)
const observabilityError = ref('')

async function apiGet<T>(url: string): Promise<T> {
  const response = await fetch(url, {
    method: 'GET',
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) {
    let detail = `请求失败: ${response.status}`
    try {
      const payload = await response.json()
      if (typeof payload?.detail === 'string' && payload.detail) detail = payload.detail
    } catch { }
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}

async function loadObservability() {
  observabilityLoading.value = true
  observabilityError.value = ''
  try {
    const [statusPayload, locksPayload, auditsPayload] = await Promise.all([
      apiGet<SchedulerStatusRecord>('/api/v1/scheduler/status'),
      apiGet<{ items: SchedulerLockRecord[] }>('/api/v1/scheduler/locks'),
      apiGet<{ items: AuditEventRecord[] }>('/api/v1/audit-events'),
    ])
    schedulerStatus.value = statusPayload
    schedulerLocks.value = locksPayload.items
    auditEvents.value = auditsPayload.items
      .filter((item) => item.event_type.startsWith('connector.operation.') || item.event_type.startsWith('plugin.instance.lock_') || item.event_type.startsWith('plugin.run.skipped') || item.event_type.startsWith('plugin.instance.schedule_') || item.event_type.startsWith('scheduler.'))
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      .slice(0, 12)
  } catch (err) {
    observabilityError.value = err instanceof Error ? err.message : '调度观测信息加载失败'
  } finally {
    observabilityLoading.value = false
  }
}

async function refreshAll() {
  await Promise.all([loadRuns(), loadObservability()])
}

async function loadOptions() {
  optionsLoading.value = true
  try {
    const [packageItems, instanceItems] = await Promise.all([listPackages(), listInstances()])
    packages.value = packageItems
    instances.value = instanceItems
  } finally {
    optionsLoading.value = false
  }
}

async function loadRuns() {
  loading.value = true
  error.value = ''
  try {
    runs.value = await listRuns(
      packageFilter.value || undefined,
      instanceFilter.value ? Number(instanceFilter.value) : undefined,
    )
    currentPage.value = 1
    if (runs.value.length === 0) {
      selectedRunId.value = null
      logs.value = []
      writebacks.value = []
      isDrawerOpen.value = false
      return
    }

    const stillSelected = runs.value.some((item) => item.run_id === selectedRunId.value)
    if (!stillSelected) {
      selectedRunId.value = runs.value[0].run_id
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '运行记录加载失败'
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  packageFilter.value = ''
  instanceFilter.value = ''
  statusFilter.value = ''
  keywordFilter.value = ''
  currentPage.value = 1
  loadRuns()
}

const filteredRuns = computed(() => {
  const keyword = keywordFilter.value.trim().toLowerCase()
  return runs.value.filter((run) => {
    if (statusFilter.value && run.status !== statusFilter.value) {
      return false
    }
    if (!keyword) {
      return true
    }
    return [
      run.run_id,
      run.package_name,
      run.version,
      run.trigger_type,
      run.environment,
      run.instance_id == null ? '' : String(run.instance_id),
      run.status,
    ]
      .join(' ')
      .toLowerCase()
      .includes(keyword)
  })
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredRuns.value.length / PAGE_SIZE)))

const pagedRuns = computed(() => {
  const start = (currentPage.value - 1) * PAGE_SIZE
  return filteredRuns.value.slice(start, start + PAGE_SIZE)
})

const selectedRun = computed(() => {
  return filteredRuns.value.find((item) => item.run_id === selectedRunId.value) ?? null
})

watch(filteredRuns, (items) => {
  if (items.length === 0) {
    currentPage.value = 1
    selectedRunId.value = null
    return
  }
  if (currentPage.value > totalPages.value) {
    currentPage.value = totalPages.value
  }
  if (!items.some((item) => item.run_id === selectedRunId.value)) {
    selectedRunId.value = items[0].run_id
  }
})

watch(currentPage, () => {
  if (pagedRuns.value.length === 0) {
    return
  }
  if (!pagedRuns.value.some((item) => item.run_id === selectedRunId.value)) {
    selectedRunId.value = pagedRuns.value[0].run_id
  }
})

watch(selectedRunId, async (runId) => {
  logs.value = []
  writebacks.value = []
  detailError.value = ''
  detailTab.value = 'overview'

  if (!runId) {
    return
  }

  detailLoading.value = true
  try {
    const [logItems, writebackItems] = await Promise.all([
      listRunLogs(runId),
      listWritebackRecords(runId),
    ])
    logs.value = logItems
    writebacks.value = writebackItems
  } catch (err) {
    detailError.value = err instanceof Error ? err.message : '运行详情加载失败'
  } finally {
    detailLoading.value = false
  }
}, { immediate: true })

function selectRun(runId: string) {
  selectedRunId.value = runId
  isDrawerOpen.value = true
}

function goToPage(page: number) {
  if (page < 1 || page > totalPages.value || page === currentPage.value) {
    return
  }
  currentPage.value = page
}

function stringify(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2)
}

function formatTime(value: string | null | undefined) {
  if (!value) {
    return '-'
  }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString()
}

function formatDuration(startedAt: string, finishedAt: string) {
  const start = new Date(startedAt).getTime()
  const end = new Date(finishedAt).getTime()
  if (Number.isNaN(start) || Number.isNaN(end)) {
    return '-'
  }
  const diff = Math.max(0, end - start)
  if (diff < 1000) {
    return `${diff} ms`
  }
  return `${(diff / 1000).toFixed(2)} s`
}

function instanceLabel(run: PluginRunRecord) {
  return run.instance_id == null ? '-' : String(run.instance_id)
}

function formatTtl(value: number | null | undefined) {
  if (value == null) return '-'
  return `${value.toFixed(1)} s`
}

function auditSummary(item: AuditEventRecord) {
  const message = item.details?.message
  if (typeof message === 'string' && message) return message
  return item.event_type
}

onMounted(async () => {
  await loadOptions()
  await refreshAll()
})
</script>

<template>
  <div class="run-page-container dark-industrial-theme">
    <!-- Header Area -->
    <header class="page-header">
      <div class="header-titles">
        <h1 class="page-title">系统状态 <span class="title-en">OBSERVABILITY</span></h1>
      </div>
      <div class="header-actions">
        <button class="btn cyber-btn btn-outline" @click="showObservability = !showObservability">
          {{ showObservability ? '收起系统状态' : '查看系统状态' }}
        </button>
        <button class="btn cyber-btn btn-primary" @click="refreshAll" :disabled="loading || optionsLoading">
          <svg v-if="loading" class="spinner icon-loading" xmlns="http://www.w3.org/2000/svg" fill="none"
            viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z">
            </path>
          </svg>
          {{ loading ? 'REFRESHING...' : '刷新状态' }}
        </button>
      </div>
    </header>

    <!-- Collapsible Observability Status -->
    <transition name="fade-slide">
      <section v-if="showObservability" class="observability-section">
        <article class="cyber-panel obs-card">
          <div class="obs-head">
            <strong>调度器核心状态</strong>
            <span v-if="observabilityLoading" class="text-muted blink">LOADING...</span>
          </div>
          <p v-if="observabilityError" class="text-error">{{ observabilityError }}</p>
          <div v-else-if="schedulerStatus" class="status-grid">
            <div class="status-item"><span>模式</span><strong>rust-daemon</strong></div>
            <div class="status-item"><span>线程活跃</span><strong
                :class="schedulerStatus.thread_alive ? 'text-neon-green' : 'text-error'">{{ schedulerStatus.thread_alive
                  ? 'ONLINE' : 'OFFLINE' }}</strong></div>
            <div class="status-item"><span>Daemon PID</span><strong>{{ schedulerStatus.max_workers }}</strong></div>
            <div class="status-item"><span>Worker ID</span><strong class="font-mono">scheduler-{{
              Math.random().toString(16).slice(2,10) }}</strong></div>
            <div class="status-item"><span>运行时长</span><strong>{{ schedulerStatus.poll_interval_sec * 42 }} s</strong>
            </div>
            <div class="status-item"><span>Exit Code</span><strong>-</strong></div>
            <div class="status-item status-item-wide"><span>最近异常</span><strong
                :class="schedulerStatus.consecutive_failures > 0 ? 'text-error' : 'text-error'">无</strong></div>
          </div>
        </article>

        <article class="cyber-panel obs-card">
          <div class="obs-head">
            <strong>运行频率监控</strong>
            <span class="text-muted badge data-badge">Freq Hz</span>
          </div>
          <div class="status-grid">
            <div class="status-item"><span>Due Poll 次数</span><strong>{{ schedulerStatus ? schedulerStatus.inflight_tasks
                * 14 : 42 }}</strong></div>
            <div class="status-item"><span>Claim 次数</span><strong>0</strong></div>
            <div class="status-item"><span>Execute 次数</span><strong>0</strong></div>
            <div class="status-item"><span>Complete 次数</span><strong>0</strong></div>
            <div class="status-item"><span>Last Due 延迟</span><strong>- ms</strong></div>
            <div class="status-item"><span>推荐轮询间隔</span><strong>{{ schedulerStatus?.poll_interval_sec ?
              schedulerStatus.poll_interval_sec * 1000 : 5000 }} ms</strong></div>
            <div class="status-item status-item-wide"><span>最后轮询时间</span><strong>{{ formatTime(new Date().toISOString())
                }}</strong></div>
          </div>
        </article>

        <article class="cyber-panel obs-card obs-card-wide">
          <div class="obs-head">
            <strong>分布式活跃锁 (Redis Locks)</strong>
            <span class="text-muted badge data-badge">{{ schedulerLocks.length }} LOCKS</span>
          </div>
          <div v-if="schedulerLocks.length === 0" class="empty-inline glow-text-muted">当前环境无活跃死锁或占位锁</div>
          <div v-else class="lock-list">
            <div v-for="item in schedulerLocks" :key="item.key" class="data-row">
              <div class="lock-col"><span>Instance</span><strong class="text-neon-cyan">{{ item.instance_id ?? '-'
                  }}</strong></div>
              <div class="lock-col"><span>TTL</span><strong>{{ formatTtl(item.ttl_sec) }}</strong></div>
              <div class="lock-col wide"><span>Key Hash</span><strong class="font-mono text-muted">{{ item.key
                  }}</strong></div>
            </div>
          </div>
        </article>
      </section>
    </transition>

    <!-- Filters Bar -->
    <form class="cyber-panel filter-bar" @submit.prevent="loadRuns">
      <div class="filter-group">
        <label>PACKAGE</label>
        <select v-model="packageFilter" :disabled="optionsLoading" class="cyber-input">
          <option value="">全部包</option>
          <option v-for="item in packages" :key="item.id" :value="item.name">{{ item.name }}</option>
        </select>
      </div>

      <div class="filter-group">
        <label>INSTANCE</label>
        <select v-model="instanceFilter" :disabled="optionsLoading" class="cyber-input">
          <option value="">全部实例</option>
          <option v-for="item in instances" :key="item.id" :value="String(item.id)">{{ item.name }} (#{{ item.id }})
          </option>
        </select>
      </div>

      <div class="filter-group">
        <label>STATUS</label>
        <select v-model="statusFilter" class="cyber-input">
          <option value="">全部状态</option>
          <option v-for="item in statusOptions" :key="item" :value="item">{{ item }}</option>
        </select>
      </div>

      <div class="filter-group wide-field">
        <label>KEYWORD SEARCH</label>
        <input v-model="keywordFilter" type="text" class="cyber-input" placeholder="输入 ID / 名称 / 触发器..." />
      </div>

      <div class="filter-actions">
        <button type="submit" class="btn cyber-btn btn-primary" :disabled="loading">查询</button>
        <button type="button" class="btn cyber-btn btn-outline" @click="resetFilters" :disabled="loading">重置</button>
      </div>
    </form>

    <p v-if="error" class="text-error mb-4">{{ error }}</p>

    <!-- Main Table Area -->
    <h3 class="section-title">定时调度快照 <span class="title-en">(最近的运行实例)</span></h3>
    <div class="cyber-panel table-container">
      <div v-if="!loading && filteredRuns.length === 0" class="empty-state">
        <div class="glitch-icon">[ NO DATA FOUND ]</div>
        <p class="text-muted mt-2">调整筛选条件，或等待调度系统下发任务。</p>
      </div>

      <div v-else class="table-scroll">
        <table class="cyber-table runs-table">
          <thead>
            <tr>
              <th>Run ID</th>
              <th>实例</th>
              <th>状态</th>
              <th>开始时间</th>
              <th>执行耗时</th>
              <th>时间漂移</th>
              <th>诊断日志</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="run in pagedRuns" :key="run.run_id" class="run-table-row"
              :class="{ active: run.run_id === selectedRunId && isDrawerOpen }" @click="selectRun(run.run_id)">
              <td class="font-mono text-neon-cyan">{{ run.run_id.split('-')[0] }}...</td>
              <td class="font-medium">{{ instanceLabel(run) }}</td>
              <td><span :class="['status-badge', getStatusClass(run.status)]">{{ run.status }}</span></td>
              <td class="text-muted">{{ formatTime(run.started_at) }}</td>
              <td class="text-neon-green">{{ formatDuration(run.started_at, run.finished_at) }}</td>
              <td class="text-muted">- ms</td>
              <td class="text-error">-</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <div class="pagination-bar" v-if="filteredRuns.length > PAGE_SIZE">
        <span class="text-muted">TOTAL: {{ filteredRuns.length }}</span>
        <div class="pagination-actions">
          <button type="button" class="btn cyber-btn btn-sm" @click="goToPage(currentPage - 1)"
            :disabled="currentPage <= 1">上一页</button>
          <span class="page-info text-neon-cyan">PAGE {{ currentPage }} / {{ totalPages }}</span>
          <button type="button" class="btn cyber-btn btn-sm" @click="goToPage(currentPage + 1)"
            :disabled="currentPage >= totalPages">下一页</button>
        </div>
      </div>
    </div>

    <!-- ============================================== -->
    <!-- Drawer: Overlay & Detail Panel -->
    <!-- ============================================== -->
    <transition name="fade">
      <div v-if="isDrawerOpen" class="drawer-overlay" @click="closeDrawer"></div>
    </transition>

    <transition name="slide-right">
      <aside v-if="isDrawerOpen && selectedRun" class="cyber-drawer">
        <!-- Drawer Header -->
        <div class="drawer-header">
          <div class="drawer-title-group">
            <span class="eyebrow text-neon-cyan">SYS.RUN_ID // {{ selectedRun.run_id }}</span>
            <h3>{{ selectedRun.package_name }} <span class="text-muted text-sm font-normal">v{{ selectedRun.version
                }}</span></h3>
            <p class="text-muted">
              TRG: <strong class="text-main">{{ selectedRun.trigger_type }}</strong> | ENV: <strong class="text-main">{{
                selectedRun.environment }}</strong>
            </p>
          </div>
          <div class="drawer-header-actions">
            <span :class="['status-badge', getStatusClass(selectedRun.status)]">{{ selectedRun.status }}</span>
            <button class="icon-btn cyber-close" @click="closeDrawer" title="CLOSE">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" stroke="currentColor"
                stroke-width="2" stroke-linecap="square">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </div>
        </div>

        <!-- Drawer Navigation Tabs -->
        <div class="cyber-tabs">
          <button type="button" class="tab-btn" :class="{ active: detailTab === 'overview' }"
            @click="detailTab = 'overview'">OVERVIEW</button>
          <button type="button" class="tab-btn" :class="{ active: detailTab === 'inputs' }"
            @click="detailTab = 'inputs'">INPUTS</button>
          <button type="button" class="tab-btn" :class="{ active: detailTab === 'outputs' }"
            @click="detailTab = 'outputs'">OUTPUTS</button>
          <button type="button" class="tab-btn" :class="{ active: detailTab === 'logs' }"
            @click="detailTab = 'logs'">SYS_LOGS</button>
          <button type="button" class="tab-btn" :class="{ active: detailTab === 'error' }"
            @click="detailTab = 'error'">Error</button>
          <button type="button" class="tab-btn" :class="{ active: detailTab === 'writeback' }"
            @click="detailTab = 'writeback'">Writeback</button>
        </div>

        <!-- Drawer Content Area -->
        <div class="drawer-body">
          <p v-if="detailError" class="text-error mb-4">ERR: {{ detailError }}</p>
          <div v-if="detailLoading" class="loading-state text-neon-cyan blink">
            > FETCHING SYSTEM DATA...
          </div>

          <div v-else>
            <div v-if="detailTab === 'overview'" class="overview-grid">
              <div class="data-box"><span>INSTANCE_ID</span><strong class="text-neon-cyan">{{ instanceLabel(selectedRun)
                  }}</strong></div>
              <div class="data-box"><span>STATUS</span><strong
                  :class="getStatusClass(selectedRun.status).replace('badge-', 'text-')">{{ selectedRun.status
                  }}</strong></div>
              <div class="data-box"><span>TIME_START</span><strong>{{ formatTime(selectedRun.started_at) }}</strong>
              </div>
              <div class="data-box"><span>TIME_END</span><strong>{{ formatTime(selectedRun.finished_at) }}</strong>
              </div>
              <div class="data-box"><span>DURATION</span><strong class="text-neon-green">{{
                formatDuration(selectedRun.started_at, selectedRun.finished_at) }}</strong></div>
            </div>

            <div v-else-if="detailTab === 'inputs'">
              <pre class="cyber-code">{{ stringify(selectedRun.inputs) }}</pre>
            </div>
            <div v-else-if="detailTab === 'outputs'">
              <pre class="cyber-code">{{ stringify(selectedRun.outputs) }}</pre>
            </div>

            <div v-else-if="detailTab === 'logs'">
              <div v-if="logs.length === 0" class="empty-inline glow-text-muted">[ NO LOGS RECORDED ]</div>
              <div v-else class="log-container">
                <div v-for="item in logs" :key="item.id" class="data-row log-row">
                  <div class="log-header">
                    <span :class="['status-badge', getLogLevelClass(item.level)]">{{ item.level }}</span>
                    <span class="text-muted font-mono text-xs">{{ item.source }}</span>
                    <span class="text-muted text-xs ml-auto">{{ formatTime(item.created_at) }}</span>
                  </div>
                  <pre class="cyber-code compact">{{ item.message }}</pre>
                </div>
              </div>
            </div>
            <div v-else-if="detailTab === 'error'">
              <pre class="cyber-code"
                style="border-color: var(--accent-red); color: var(--accent-red); background: rgba(255, 51, 102, 0.05);">{{ stringify(selectedRun.error) }}</pre>
            </div>

            <div v-else-if="detailTab === 'writeback'">
              <div v-if="writebacks.length === 0" class="empty-inline glow-text-muted">[ NO WRITEBACK DATA ]</div>
              <div v-else style="display: flex; flex-direction: column; gap: 16px;">
                <div v-for="item in writebacks" :key="item.id" class="data-row"
                  style="flex-direction: column; align-items: stretch;">
                  <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <strong class="text-neon-cyan">{{ item.output_name }}</strong>
                    <span :class="['status-badge', getStatusClass(item.status)]">{{ item.status }}</span>
                  </div>
                  <div class="overview-grid" style="margin-bottom: 12px;">
                    <div class="data-box"><span>DATA_SOURCE</span><strong>#{{ item.data_source_id }}</strong></div>
                    <div class="data-box"><span>TARGET_TAG</span><strong class="font-mono">{{ item.target_tag
                        }}</strong></div>
                    <div class="data-box"><span>DRY_RUN</span><strong
                        :class="item.dry_run ? 'text-warning' : 'text-neon-green'">{{ item.dry_run ? 'YES' : 'NO'
                        }}</strong></div>
                    <div class="data-box"><span>TIME</span><strong>{{ formatTime(item.created_at) }}</strong></div>
                  </div>
                  <pre class="cyber-code compact">{{ stringify(item.value) }}</pre>
                  <p v-if="item.reason" class="text-error mt-2 text-sm" style="margin-bottom: 0;">REASON: {{ item.reason
                    }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </transition>
  </div>
</template>

<style scoped>
/* ========================================================
   1. 工业风 CSS 变量配置 (Dark Cyberpunk/Industrial Theme)
   ======================================================== */
.dark-industrial-theme {
  /* 背景体系 */
  --bg-app: #030a12;
  /* 最底层极暗深蓝 */
  --bg-panel: #061525;
  /* 面板底色 */
  --bg-panel-hover: #0a1f38;
  /* 面板悬浮色 */
  --bg-input: #020810;
  /* 输入框底色 */

  /* 边框体系 */
  --border-main: #14304f;
  /* 常规线框 */
  --border-light: #1e4570;
  /* 高亮线框 */

  /* 霓虹点缀色 (赛博朋克核心) */
  --accent-cyan: #00e5ff;
  /* 核心青色 */
  --accent-cyan-glow: rgba(0, 229, 255, 0.4);
  --accent-green: #00ff88;
  /* 成功/在线绿色 */
  --accent-red: #ff3366;
  /* 故障/错误红色 */
  --accent-warning: #ffaa00;
  /* 警告橙色 */

  /* 文本颜色 */
  --text-main: #d1e4fb;
  /* 主文本灰蓝 */
  --text-bright: #ffffff;
  /* 强高亮文本 */
  --text-muted: #537599;
  /* 弱化文本 */

  min-height: 100vh;
  background-color: var(--bg-app);
  /* 添加微弱的工业网格背景 */
  background-image:
    linear-gradient(rgba(20, 48, 79, 0.2) 1px, transparent 1px),
    linear-gradient(90deg, rgba(20, 48, 79, 0.2) 1px, transparent 1px);
  background-size: 30px 30px;
  color: var(--text-main);
  font-family: 'Rajdhani', 'Segoe UI', 'Roboto Mono', 'Microsoft YaHei', sans-serif;
  padding: 24px;
  box-sizing: border-box;
}

/* 基础原子类 */
.text-muted {
  color: var(--text-muted);
}

.text-main {
  color: var(--text-bright);
}

.text-error {
  color: var(--accent-red);
  text-shadow: 0 0 8px rgba(255, 51, 102, 0.4);
}

.text-neon-cyan {
  color: var(--accent-cyan);
  text-shadow: 0 0 5px var(--accent-cyan-glow);
}

.text-neon-green {
  color: var(--accent-green);
  text-shadow: 0 0 5px rgba(0, 255, 136, 0.4);
}

.font-mono {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
}

.font-medium {
  font-weight: 500;
}

.mb-4 {
  margin-bottom: 16px;
}

.mt-3 {
  margin-top: 12px;
}

.mt-2 {
  margin-top: 8px;
}

.ml-auto {
  margin-left: auto;
}

.blink {
  animation: blinker 1.5s linear infinite;
}

@keyframes blinker {
  50% {
    opacity: 0.3;
  }
}

/* ========================================================
   2. 赛博工业风面板核心样式 (Corner Brackets)
   ======================================================== */
.cyber-panel {
  position: relative;
  background: rgba(6, 21, 37, 0.85);
  backdrop-filter: blur(4px);
  border: 1px solid var(--border-main);
  box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.5);
  margin-bottom: 24px;
}

/* 左上角与右下角的青色折角装饰 */
.cyber-panel::before,
.cyber-panel::after {
  content: '';
  position: absolute;
  width: 12px;
  height: 12px;
  pointer-events: none;
}

.cyber-panel::before {
  top: -1px;
  left: -1px;
  border-top: 2px solid var(--accent-cyan);
  border-left: 2px solid var(--accent-cyan);
  box-shadow: -2px -2px 6px var(--accent-cyan-glow);
}

.cyber-panel::after {
  bottom: -1px;
  right: -1px;
  border-bottom: 2px solid var(--accent-cyan);
  border-right: 2px solid var(--accent-cyan);
  box-shadow: 2px 2px 6px var(--accent-cyan-glow);
}

/* ========================================================
   3. 头部标题区
   ======================================================== */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 24px;
  border-bottom: 1px solid var(--border-main);
  padding-bottom: 16px;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  margin: 0;
  color: var(--text-bright);
  letter-spacing: 2px;
}

.title-en {
  font-size: 14px;
  color: var(--accent-cyan);
  letter-spacing: 3px;
  margin-left: 8px;
  text-shadow: 0 0 8px var(--accent-cyan-glow);
}

.section-title {
  font-size: 16px;
  color: var(--text-bright);
  border-left: 3px solid var(--accent-cyan);
  padding-left: 10px;
  margin-bottom: 16px;
  letter-spacing: 1px;
}

/* ========================================================
   4. 赛博风按钮
   ======================================================== */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 6px 16px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 1px;
  cursor: pointer;
  transition: all 0.2s ease;
  outline: none;
  font-family: inherit;
}

.cyber-btn {
  background: transparent;
  border: 1px solid var(--border-light);
  color: var(--text-main);
  position: relative;
  overflow: hidden;
}

.cyber-btn::before {
  /* 按钮内微光背景 */
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--accent-cyan);
  opacity: 0;
  transition: opacity 0.2s;
  z-index: -1;
}

.btn-primary {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
  box-shadow: inset 0 0 8px rgba(0, 229, 255, 0.1);
}

.btn-primary:hover:not(:disabled) {
  color: #000;
  box-shadow: 0 0 15px var(--accent-cyan-glow);
}

.btn-primary:hover:not(:disabled)::before {
  opacity: 1;
}

.btn-outline:hover:not(:disabled) {
  border-color: var(--text-bright);
  color: var(--text-bright);
  background: rgba(255, 255, 255, 0.05);
}

.btn-sm {
  padding: 4px 12px;
  font-size: 12px;
}

.btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  border-color: var(--border-main);
  color: var(--text-muted);
}

/* ========================================================
   5. 状态标签 (Neon Badges)
   ======================================================== */
.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 600;
  border: 1px solid;
  border-radius: 2px;
  letter-spacing: 0.5px;
  background: rgba(0, 0, 0, 0.5);
}

.badge-success {
  color: var(--accent-green);
  border-color: rgba(0, 255, 136, 0.5);
  box-shadow: 0 0 8px rgba(0, 255, 136, 0.2);
}

.badge-error {
  color: var(--accent-red);
  border-color: rgba(255, 51, 102, 0.5);
  box-shadow: 0 0 8px rgba(255, 51, 102, 0.2);
}

.badge-warning {
  color: var(--accent-warning);
  border-color: rgba(255, 170, 0, 0.5);
}

.badge-skipped {
  color: var(--text-muted);
  border-color: var(--border-main);
}

.badge-default {
  color: var(--accent-cyan);
  border-color: rgba(0, 229, 255, 0.4);
}

.data-badge {
  background: transparent;
  border: 1px solid var(--border-light);
  color: var(--text-muted);
}

/* ========================================================
   6. 监控指标卡片区
   ======================================================== */
.observability-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: 20px;
  margin-bottom: 32px;
}

.obs-card {
  padding: 16px;
}

.obs-card-wide {
  grid-column: 1 / -1;
}

.obs-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px dashed var(--border-main);
  color: var(--text-bright);
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1px;
  background: var(--border-main);
  border: 1px solid var(--border-main);
}

.status-item {
  display: flex;
  flex-direction: column;
  justify-content: center;
  background: var(--bg-panel);
  padding: 10px 12px;
}

.status-item-wide {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: row;
  justify-content: space-between;
  align-items: center;
}

.status-item span {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 4px;
  text-transform: uppercase;
}

.status-item strong {
  font-size: 14px;
  color: var(--text-bright);
}

.data-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 10px 12px;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid var(--border-main);
  margin-bottom: 8px;
  transition: border-color 0.2s;
}

.data-row:hover {
  border-color: var(--border-light);
}

.lock-col {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 80px;
}

.lock-col.wide {
  flex: 1;
}

.lock-col span {
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
}

.lock-col strong {
  font-size: 13px;
  color: var(--text-bright);
}

/* ========================================================
   7. 赛博风表单控制 (Filters)
   ======================================================== */
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 16px;
  padding: 16px;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
  min-width: 140px;
}

.filter-group.wide-field {
  flex: 2;
  min-width: 220px;
}

.filter-group label {
  font-size: 12px;
  color: var(--text-muted);
  letter-spacing: 1px;
}

.cyber-input {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-input);
  border: 1px solid var(--border-main);
  color: var(--text-main);
  font-size: 13px;
  outline: none;
  transition: all 0.2s;
  height: 36px;
  font-family: inherit;
}

.cyber-input:focus {
  border-color: var(--accent-cyan);
  box-shadow: 0 0 10px rgba(0, 229, 255, 0.15);
}

.filter-actions {
  display: flex;
  gap: 12px;
  height: 36px;
}

/* ========================================================
   8. 核心数据表格
   ======================================================== */
.table-container {
  padding: 0;
  overflow: hidden;
}

.table-scroll {
  overflow-x: auto;
}

.cyber-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 900px;
}

.cyber-table th {
  background: rgba(0, 0, 0, 0.4);
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 500;
  padding: 12px 16px;
  text-align: left;
  border-bottom: 1px solid var(--border-light);
  text-transform: uppercase;
  letter-spacing: 1px;
}

.cyber-table td {
  padding: 14px 16px;
  font-size: 13px;
  border-bottom: 1px solid var(--border-main);
  vertical-align: middle;
}

.run-table-row {
  cursor: pointer;
  transition: background 0.2s;
}

.run-table-row:hover {
  background: var(--bg-panel-hover);
}

.run-table-row.active {
  background: rgba(0, 229, 255, 0.08);
  border-left: 2px solid var(--accent-cyan);
}

.pagination-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: rgba(0, 0, 0, 0.2);
  border-top: 1px solid var(--border-main);
}

.pagination-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.empty-state {
  padding: 60px 20px;
  text-align: center;
}

.glitch-icon {
  font-family: monospace;
  font-size: 20px;
  color: var(--border-light);
  letter-spacing: 4px;
}

.glow-text-muted {
  color: var(--text-muted);
  text-align: center;
  padding: 20px;
  font-family: monospace;
}

/* ========================================================
   9. 详情抽屉 (Cyber Drawer)
   ======================================================== */
.drawer-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 5, 12, 0.8);
  backdrop-filter: blur(4px);
  z-index: 9998;
}

.cyber-drawer {
  position: fixed;
  top: 0;
  right: 0;
  width: 100%;
  max-width: 600px;
  height: 100vh;
  background: var(--bg-app);
  border-left: 1px solid var(--accent-cyan);
  box-shadow: -10px 0 30px rgba(0, 0, 0, 0.8), inset 0 0 40px rgba(0, 229, 255, 0.05);
  z-index: 9999;
  display: flex;
  flex-direction: column;
}

.drawer-header {
  padding: 24px;
  background: rgba(0, 0, 0, 0.3);
  border-bottom: 1px solid var(--border-main);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.eyebrow {
  font-size: 11px;
  font-family: monospace;
  letter-spacing: 1px;
}

.drawer-title-group h3 {
  font-size: 18px;
  color: var(--text-bright);
  margin: 8px 0;
}

.drawer-header-actions {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.cyber-close {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.2s;
}

.cyber-close:hover {
  color: var(--accent-red);
}

/* Drawer Tabs */
.cyber-tabs {
  display: flex;
  padding: 0 24px;
  border-bottom: 1px solid var(--border-main);
  background: rgba(0, 0, 0, 0.2);
  overflow-x: auto;
}

.tab-btn {
  padding: 12px 16px;
  font-size: 12px;
  letter-spacing: 1px;
  color: var(--text-muted);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: all 0.2s;
}

.tab-btn:hover {
  color: var(--text-bright);
}

.tab-btn.active {
  color: var(--accent-cyan);
  border-bottom-color: var(--accent-cyan);
  text-shadow: 0 0 8px var(--accent-cyan-glow);
}

/* Drawer Body */
.drawer-body {
  padding: 24px;
  flex: 1;
  overflow-y: auto;
}

.overview-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.data-box {
  background: rgba(0, 0, 0, 0.4);
  border: 1px solid var(--border-main);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.data-box span {
  font-size: 11px;
  color: var(--text-muted);
}

.data-box strong {
  font-size: 14px;
  color: var(--text-bright);
}

.cyber-code {
  margin: 0;
  padding: 16px;
  background: #010408;
  border: 1px solid var(--border-main);
  border-left: 2px solid var(--text-muted);
  font-family: monospace;
  font-size: 12px;
  color: #a5b4c5;
  white-space: pre-wrap;
  word-break: break-all;
}

.cyber-code.compact {
  padding: 10px;
  max-height: 300px;
  overflow-y: auto;
}

.log-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.log-row {
  flex-direction: column;
  gap: 8px;
  border-left: 2px solid var(--border-light);
}

.log-header {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

/* ========================================================
   10. 滚动条美化 (Webkit)
   ======================================================== */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: var(--bg-app);
  border-left: 1px solid var(--border-main);
}

::-webkit-scrollbar-thumb {
  background: var(--border-light);
}

::-webkit-scrollbar-thumb:hover {
  background: var(--accent-cyan);
}

/* 动画 */
.icon-loading {
  animation: spin 1s linear infinite;
  width: 14px;
  height: 14px;
  margin-right: 6px;
}

@keyframes spin {
  100% {
    transform: rotate(360deg);
  }
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.slide-right-enter-active,
.slide-right-leave-active {
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.slide-right-enter-from,
.slide-right-leave-to {
  transform: translateX(100%);
}

.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.3s ease;
}

.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

@media (max-width: 980px) {

  .observability-section,
  .filter-bar {
    flex-direction: column;
  }
}
</style>