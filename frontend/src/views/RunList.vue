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

const statusOptions =['COMPLETED', 'PARTIAL_SUCCESS', 'FAILED', 'TIMED_OUT', 'SKIPPED']

// =======================
// 新增的 UI 交互状态
// =======================
const isDrawerOpen = ref(false)
const showObservability = ref(false)

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
    } catch {}
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
      writebacks.value =[]
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
    return[
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
  logs.value =[]
  writebacks.value =[]
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
  <div class="run-page-container">
    <!-- Header Area -->
    <header class="page-header">
      <div class="header-titles">
        <h1 class="page-title">运行记录</h1>
        <p class="page-subtitle">监控与查看插件和实例的执行历史。点击表格中的任意记录即可在右侧查看详情。</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-outline" @click="showObservability = !showObservability">
          {{ showObservability ? '收起系统状态' : '查看系统状态' }}
        </button>
        <button class="btn btn-primary" @click="refreshAll" :disabled="loading || optionsLoading">
          <svg v-if="loading" class="spinner icon-loading" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          {{ loading ? '刷新中...' : '刷新' }}
        </button>
      </div>
    </header>

    <!-- Collapsible Observability Status -->
    <transition name="fade-slide">
      <section v-if="showObservability" class="observability-section">
        <article class="obs-card">
          <div class="obs-head">
            <strong>调度器状态</strong>
            <span v-if="observabilityLoading" class="text-muted">刷新中</span>
          </div>
          <p v-if="observabilityError" class="text-error">{{ observabilityError }}</p>
          <div v-else-if="schedulerStatus" class="status-grid">
            <div class="status-item"><span>线程存活</span><strong>{{ schedulerStatus.thread_alive ? 'Yes' : 'No' }}</strong></div>
            <div class="status-item"><span>轮询间隔</span><strong>{{ schedulerStatus.poll_interval_sec }} s</strong></div>
            <div class="status-item"><span>工作线程</span><strong>{{ schedulerStatus.max_workers }}</strong></div>
            <div class="status-item"><span>执行中</span><strong>{{ schedulerStatus.inflight_tasks }}</strong></div>
            <div class="status-item"><span>活跃锁</span><strong>{{ schedulerStatus.active_lock_count }}</strong></div>
            <div class="status-item"><span>连续失败</span><strong>{{ schedulerStatus.consecutive_failures }}</strong></div>
          </div>
          <p v-if="schedulerStatus?.lock_observation_error" class="text-muted mt-3">锁扫描异常：{{ schedulerStatus.lock_observation_error }}</p>
          <p v-if="schedulerStatus?.last_error" class="text-muted mt-2">最近错误：{{ schedulerStatus.last_error }}</p>
        </article>

        <article class="obs-card">
          <div class="obs-head">
            <strong>Redis 活跃锁</strong>
            <span class="text-muted badge">{{ schedulerLocks.length }} 条</span>
          </div>
          <div v-if="schedulerLocks.length === 0" class="empty-inline">当前无活跃实例锁</div>
          <div v-else class="lock-list">
            <div v-for="item in schedulerLocks" :key="item.key" class="lock-row">
              <div class="lock-col"><span>实例</span><strong>{{ item.instance_id ?? '-' }}</strong></div>
              <div class="lock-col"><span>TTL</span><strong>{{ formatTtl(item.ttl_sec) }}</strong></div>
              <div class="lock-col wide"><span>Key</span><strong>{{ item.key }}</strong></div>
            </div>
          </div>
        </article>

        <article class="obs-card obs-card-wide">
          <div class="obs-head">
            <strong>最近调度 / 锁 / 连接器事件</strong>
            <span class="text-muted badge">{{ auditEvents.length }} 条</span>
          </div>
          <div v-if="auditEvents.length === 0" class="empty-inline">暂无相关审计事件</div>
          <div v-else class="audit-list">
            <div v-for="item in auditEvents" :key="item.id" class="audit-row">
              <div class="audit-meta">
                <strong class="text-main">{{ item.event_type }}</strong>
                <span>{{ item.target_type }} / {{ item.target_id }}</span>
                <span>{{ formatTime(item.created_at) }}</span>
              </div>
              <p class="text-muted audit-summary">{{ auditSummary(item) }}</p>
            </div>
          </div>
        </article>
      </section>
    </transition>

    <!-- Filters Bar -->
    <form class="filter-bar" @submit.prevent="loadRuns">
      <div class="filter-group">
        <label>包名 (Package)</label>
        <select v-model="packageFilter" :disabled="optionsLoading" class="form-control">
          <option value="">全部包</option>
          <option v-for="item in packages" :key="item.id" :value="item.name">{{ item.name }}</option>
        </select>
      </div>

      <div class="filter-group">
        <label>实例 (Instance)</label>
        <select v-model="instanceFilter" :disabled="optionsLoading" class="form-control">
          <option value="">全部实例</option>
          <option v-for="item in instances" :key="item.id" :value="String(item.id)">{{ item.name }} (#{{ item.id }})</option>
        </select>
      </div>

      <div class="filter-group">
        <label>状态 (Status)</label>
        <select v-model="statusFilter" class="form-control">
          <option value="">全部状态</option>
          <option v-for="item in statusOptions" :key="item" :value="item">{{ item }}</option>
        </select>
      </div>

      <div class="filter-group wide-field">
        <label>关键字搜索</label>
        <input v-model="keywordFilter" type="text" class="form-control" placeholder="支持 run_id / package / trigger 等" />
      </div>

      <div class="filter-actions">
        <button type="submit" class="btn btn-primary" :disabled="loading">查询</button>
        <button type="button" class="btn btn-outline" @click="resetFilters" :disabled="loading">重置</button>
      </div>
    </form>

    <p v-if="error" class="text-error mb-4">{{ error }}</p>

    <!-- Main Table Area -->
    <div v-if="!loading && filteredRuns.length === 0" class="empty-state">
      <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" fill="none" viewBox="0 0 24 24" stroke="#cbd5e1" class="mb-4">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path>
      </svg>
      <h3>暂无运行记录</h3>
      <p>调整筛选条件，或先执行一次插件/实例运行以生成数据。</p>
    </div>

    <div v-else class="table-container">
      <div class="table-scroll">
        <table class="runs-table">
          <thead>
            <tr>
              <th>Run ID</th>
              <th>包名</th>
              <th>版本</th>
              <th>实例</th>
              <th>触发方式</th>
              <th>状态</th>
              <th>开始时间</th>
              <th>耗时</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="run in pagedRuns"
              :key="run.run_id"
              class="run-table-row"
              :class="{ active: run.run_id === selectedRunId && isDrawerOpen }"
              @click="selectRun(run.run_id)"
            >
              <td class="font-mono">{{ run.run_id.split('-')[0] }}...</td>
              <td class="font-medium">{{ run.package_name }}</td>
              <td>{{ run.version }}</td>
              <td>{{ instanceLabel(run) }}</td>
              <td><span class="badge badge-default">{{ run.trigger_type }}</span></td>
              <td><span :class="['badge', getStatusClass(run.status)]">{{ run.status }}</span></td>
              <td class="text-muted">{{ formatTime(run.started_at) }}</td>
              <td>{{ formatDuration(run.started_at, run.finished_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <div class="pagination-bar" v-if="filteredRuns.length > PAGE_SIZE">
        <span class="text-muted">共 {{ filteredRuns.length }} 条记录</span>
        <div class="pagination-actions">
          <button type="button" class="btn btn-outline btn-sm" @click="goToPage(currentPage - 1)" :disabled="currentPage <= 1">上一页</button>
          <span class="page-info">第 {{ currentPage }} / {{ totalPages }} 页</span>
          <button type="button" class="btn btn-outline btn-sm" @click="goToPage(currentPage + 1)" :disabled="currentPage >= totalPages">下一页</button>
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
      <aside v-if="isDrawerOpen && selectedRun" class="detail-drawer">
        <!-- Drawer Header -->
        <div class="drawer-header">
          <div class="drawer-title-group">
            <span class="eyebrow">Run ID: {{ selectedRun.run_id }}</span>
            <h3>{{ selectedRun.package_name }} <span class="text-muted text-sm font-normal">@ {{ selectedRun.version }}</span></h3>
            <p>
              触发: <strong>{{ selectedRun.trigger_type }}</strong> · 环境: <strong>{{ selectedRun.environment }}</strong> · 尝试: <strong>{{ selectedRun.attempt }}</strong>
            </p>
          </div>
          <div class="drawer-header-actions">
            <span :class="['badge', getStatusClass(selectedRun.status)]">{{ selectedRun.status }}</span>
            <button class="icon-btn" @click="closeDrawer" title="关闭详情">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </div>
        </div>

        <!-- Drawer Navigation Tabs -->
        <div class="drawer-tabs">
          <button type="button" class="tab-btn" :class="{ active: detailTab === 'overview' }" @click="detailTab = 'overview'">概览</button>
          <button type="button" class="tab-btn" :class="{ active: detailTab === 'inputs' }" @click="detailTab = 'inputs'">Inputs</button>
          <button type="button" class="tab-btn" :class="{ active: detailTab === 'outputs' }" @click="detailTab = 'outputs'">Outputs</button>
          <button type="button" class="tab-btn" :class="{ active: detailTab === 'metrics' }" @click="detailTab = 'metrics'">Metrics</button>
          <button type="button" class="tab-btn" :class="{ active: detailTab === 'error' }" @click="detailTab = 'error'">Error</button>
          <button type="button" class="tab-btn" :class="{ active: detailTab === 'logs' }" @click="detailTab = 'logs'">Logs</button>
          <button type="button" class="tab-btn" :class="{ active: detailTab === 'writeback' }" @click="detailTab = 'writeback'">Writeback</button>
        </div>

        <!-- Drawer Content Area -->
        <div class="drawer-body">
          <p v-if="detailError" class="text-error mb-4">{{ detailError }}</p>
          <div v-if="detailLoading" class="loading-state">
             <svg class="spinner icon-loading mr-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
             正在加载详情...
          </div>

          <div v-else>
            <div v-if="detailTab === 'overview'" class="overview-grid">
              <div class="info-box"><span>实例 ID</span><strong>{{ instanceLabel(selectedRun) }}</strong></div>
              <div class="info-box"><span>状态</span><strong :class="['text-' + getStatusClass(selectedRun.status).replace('badge-', '')]">{{ selectedRun.status }}</strong></div>
              <div class="info-box"><span>开始时间</span><strong>{{ formatTime(selectedRun.started_at) }}</strong></div>
              <div class="info-box"><span>结束时间</span><strong>{{ formatTime(selectedRun.finished_at) }}</strong></div>
              <div class="info-box"><span>环境</span><strong>{{ selectedRun.environment }}</strong></div>
              <div class="info-box"><span>耗时</span><strong>{{ formatDuration(selectedRun.started_at, selectedRun.finished_at) }}</strong></div>
            </div>

            <div v-else-if="detailTab === 'inputs'"><pre class="code-block">{{ stringify(selectedRun.inputs) }}</pre></div>
            <div v-else-if="detailTab === 'outputs'"><pre class="code-block">{{ stringify(selectedRun.outputs) }}</pre></div>
            <div v-else-if="detailTab === 'metrics'"><pre class="code-block">{{ stringify(selectedRun.metrics) }}</pre></div>
            <div v-else-if="detailTab === 'error'"><pre class="code-block error-block">{{ stringify(selectedRun.error) }}</pre></div>

            <div v-else-if="detailTab === 'logs'">
              <div v-if="logs.length === 0" class="empty-inline">暂无日志</div>
              <div v-else class="log-container">
                <div v-for="item in logs" :key="item.id" class="log-card">
                  <div class="log-header">
                    <span :class="['badge', getLogLevelClass(item.level)]">{{ item.level }}</span>
                    <span class="text-muted font-mono text-xs">{{ item.source }}</span>
                    <span class="text-muted text-xs ml-auto">{{ formatTime(item.created_at) }}</span>
                  </div>
                  <pre class="code-block compact">{{ item.message }}</pre>
                </div>
              </div>
            </div>

            <div v-else-if="detailTab === 'writeback'">
              <div v-if="writebacks.length === 0" class="empty-inline">暂无写回记录</div>
              <div v-else class="writeback-container">
                <div v-for="item in writebacks" :key="item.id" class="writeback-card">
                  <div class="writeback-header">
                    <strong>{{ item.output_name }}</strong>
                    <span :class="['badge', getStatusClass(item.status)]">{{ item.status }}</span>
                  </div>
                  <div class="writeback-grid">
                    <div class="wb-info"><span>目标数据源</span><strong>#{{ item.data_source_id }}</strong></div>
                    <div class="wb-info"><span>目标标签</span><strong class="font-mono">{{ item.target_tag }}</strong></div>
                    <div class="wb-info"><span>Dry Run</span><strong>{{ item.dry_run ? 'Yes' : 'No' }}</strong></div>
                    <div class="wb-info"><span>时间</span><strong>{{ formatTime(item.created_at) }}</strong></div>
                  </div>
                  <pre class="code-block compact mt-3">{{ stringify(item.value) }}</pre>
                  <p v-if="item.reason" class="text-muted mt-2 text-sm">原因：{{ item.reason }}</p>
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
   1. Base Setup & Typography
   ======================================================== */
.run-page-container {
  max-width: 1440px;
  margin: 0 auto;
  padding: 24px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  color: #0f172a;
}
.text-muted { color: #64748b; }
.text-main { color: #334155; }
.text-error { color: #dc2626; }
.text-success { color: #16a34a; }
.text-warning { color: #d97706; }
.text-sm { font-size: 13px; }
.font-mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
.font-medium { font-weight: 500; }
.mb-4 { margin-bottom: 16px; }
.mt-3 { margin-top: 12px; }
.mt-2 { margin-top: 8px; }
.ml-auto { margin-left: auto; }

/* ========================================================
   2. Header & Top Level
   ======================================================== */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 24px;
}
.page-title {
  font-size: 24px;
  font-weight: 700;
  margin: 0 0 4px 0;
  color: #0f172a;
}
.page-subtitle {
  font-size: 14px;
  color: #64748b;
  margin: 0;
}
.header-actions {
  display: flex;
  gap: 12px;
}

/* ========================================================
   3. Buttons
   ======================================================== */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid transparent;
  outline: none;
}
.btn-primary {
  background: #2563eb;
  color: #ffffff;
  box-shadow: 0 1px 2px rgba(37, 99, 235, 0.2);
}
.btn-primary:hover:not(:disabled) {
  background: #1d4ed8;
}
.btn-outline {
  background: #ffffff;
  border-color: #cbd5e1;
  color: #334155;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}
.btn-outline:hover:not(:disabled) {
  background: #f8fafc;
  border-color: #94a3b8;
}
.btn-sm {
  padding: 6px 12px;
  font-size: 13px;
}
.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.icon-btn {
  background: transparent;
  border: none;
  color: #64748b;
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  transition: background 0.2s, color 0.2s;
}
.icon-btn:hover {
  background: #f1f5f9;
  color: #0f172a;
}

/* ========================================================
   4. Status Badges
   ======================================================== */
.badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 9999px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
}
.badge-success { background: #dcfce7; color: #166534; }
.badge-error { background: #fee2e2; color: #991b1b; }
.badge-warning { background: #fef9c3; color: #854d0e; }
.badge-skipped { background: #f1f5f9; color: #475569; }
.badge-default { background: #e0e7ff; color: #3730a3; }

/* ========================================================
   5. Observability Section
   ======================================================== */
.observability-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 20px;
  margin-bottom: 24px;
}
.obs-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
}
.obs-card-wide {
  grid-column: 1 / -1;
}
.obs-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f1f5f9;
}
.obs-head strong { font-size: 15px; }
.status-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
.status-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: #f8fafc;
  padding: 12px;
  border-radius: 8px;
}
.status-item span { font-size: 12px; color: #64748b; }
.status-item strong { font-size: 14px; color: #334155; }
.lock-list, .audit-list { display: grid; gap: 12px; }
.lock-row, .audit-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}
.lock-col {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 80px;
}
.lock-col.wide { flex: 1; }
.lock-col span { font-size: 12px; color: #64748b; }
.lock-col strong { font-size: 13px; color: #334155; }
.audit-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  font-size: 13px;
  width: 100%;
}
.audit-summary { margin: 0; font-size: 13px; }

/* ========================================================
   6. Filters Bar
   ======================================================== */
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 16px;
  background: #ffffff;
  padding: 16px 20px;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  margin-bottom: 24px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
}
.filter-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
  min-width: 160px;
}
.filter-group.wide-field {
  flex: 2;
  min-width: 250px;
}
.filter-group label {
  font-size: 13px;
  font-weight: 500;
  color: #475569;
}
.form-control {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-size: 14px;
  color: #334155;
  background: #f8fafc;
  transition: all 0.2s;
  height: 38px;
}
.form-control:focus {
  outline: none;
  border-color: #3b82f6;
  background: #ffffff;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}
.filter-actions {
  display: flex;
  gap: 12px;
}

/* ========================================================
   7. Main Data Table
   ======================================================== */
.table-container {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
  overflow: hidden;
}
.table-scroll { overflow-x: auto; }
.runs-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  min-width: 900px;
}
.runs-table th {
  background: #f8fafc;
  color: #64748b;
  font-weight: 600;
  font-size: 13px;
  padding: 14px 20px;
  text-align: left;
  border-bottom: 1px solid #e2e8f0;
  white-space: nowrap;
}
.runs-table td {
  padding: 16px 20px;
  font-size: 14px;
  color: #334155;
  border-bottom: 1px solid #f1f5f9;
  vertical-align: middle;
}
.run-table-row {
  cursor: pointer;
  transition: background 0.15s ease;
}
.run-table-row:hover { background: #f8fafc; }
.run-table-row.active { background: #eff6ff; }

/* Pagination */
.pagination-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: #ffffff;
  border-top: 1px solid #e2e8f0;
}
.pagination-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}
.page-info {
  font-size: 13px;
  color: #64748b;
}

/* ========================================================
   8. Detail Drawer (Offcanvas)
   ======================================================== */
.drawer-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(15, 23, 42, 0.4);
  z-index: 9998;
  backdrop-filter: blur(2px);
}
.detail-drawer {
  position: fixed;
  top: 0; right: 0;
  width: 100%; max-width: 650px;
  height: 100vh;
  background: #ffffff;
  z-index: 9999;
  box-shadow: -8px 0 30px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
}
.drawer-header {
  padding: 24px 32px;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.drawer-title-group h3 {
  font-size: 20px;
  font-weight: 700;
  color: #0f172a;
  margin: 4px 0 8px 0;
}
.drawer-title-group p { font-size: 13px; color: #64748b; margin: 0; }
.eyebrow {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  color: #64748b;
  letter-spacing: 0.5px;
}
.drawer-header-actions { display: flex; align-items: flex-start; gap: 16px; }

/* Drawer Tabs */
.drawer-tabs {
  display: flex;
  gap: 8px;
  padding: 0 32px;
  border-bottom: 1px solid #e2e8f0;
  background: #ffffff;
  overflow-x: auto;
}
.tab-btn {
  padding: 16px 12px;
  font-size: 14px;
  font-weight: 500;
  color: #64748b;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}
.tab-btn:hover { color: #0f172a; }
.tab-btn.active {
  color: #2563eb;
  border-bottom-color: #2563eb;
}

/* Drawer Body & Content */
.drawer-body {
  padding: 24px 32px;
  flex: 1;
  overflow-y: auto;
  background: #ffffff;
}
.overview-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}
.info-box {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 16px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}
.info-box span { font-size: 12px; color: #64748b; }
.info-box strong { font-size: 14px; color: #0f172a; }
.code-block {
  margin: 0;
  padding: 16px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-family: ui-monospace, monospace;
  font-size: 13px;
  color: #334155;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
.code-block.compact {
  padding: 12px;
  max-height: 250px;
  overflow-y: auto;
}
.error-block {
  background: #fef2f2;
  border-color: #fecaca;
  color: #991b1b;
}

/* Logs & Writebacks */
.log-container, .writeback-container { display: grid; gap: 16px; }
.log-card, .writeback-card {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 16px;
}
.log-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.writeback-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.writeback-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.wb-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: #f8fafc;
  padding: 10px;
  border-radius: 6px;
}
.wb-info span { font-size: 12px; color: #64748b; }
.wb-info strong { font-size: 13px; color: #334155; }
.empty-inline {
  padding: 24px;
  text-align: center;
  color: #64748b;
  background: #f8fafc;
  border: 1px dashed #cbd5e1;
  border-radius: 8px;
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  background: #f8fafc;
  border: 1px dashed #cbd5e1;
  border-radius: 12px;
  color: #64748b;
}
.empty-state h3 { font-size: 18px; color: #334155; margin-bottom: 8px; }

/* ========================================================
   9. Utilities & Animations
   ======================================================== */
.opacity-25 { opacity: 0.25; }
.opacity-75 { opacity: 0.75; }
.icon-loading {
  animation: spin 1s linear infinite;
  width: 16px; height: 16px;
  margin-right: 8px;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.slide-right-enter-active, .slide-right-leave-active { transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
.slide-right-enter-from, .slide-right-leave-to { transform: translateX(100%); }

.fade-slide-enter-active, .fade-slide-leave-active { transition: all 0.3s ease; }
.fade-slide-enter-from, .fade-slide-leave-to { opacity: 0; transform: translateY(-10px); }

@media (max-width: 980px) {
  .observability-section, .filter-bar { flex-direction: column; }
  .filter-group { min-width: 100%; }
}
</style>