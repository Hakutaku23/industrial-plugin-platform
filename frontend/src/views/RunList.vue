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
      writebacks.value = []
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
  <section class="panel run-page">
    <div class="intro page-heading">
      <div>
        <p class="eyebrow">Runs</p>
        <h2>运行记录</h2>
        <p>以查询表方式查看运行概要。点击某一条记录后，再在右侧查看完整详情。</p>
      </div>
      <button type="button" class="secondary-button" @click="refreshAll" :disabled="loading || optionsLoading">
        {{ loading ? '刷新中' : '刷新' }}
      </button>
    </div>

    <section class="observability-grid">
      <article class="obs-card">
        <div class="obs-head">
          <strong>调度器状态</strong>
          <span v-if="observabilityLoading" class="muted">刷新中</span>
        </div>
        <p v-if="observabilityError" class="error">{{ observabilityError }}</p>
        <div v-else-if="schedulerStatus" class="status-grid">
          <div><span>线程存活</span><strong>{{ schedulerStatus.thread_alive ? 'Yes' : 'No' }}</strong></div>
          <div><span>轮询间隔</span><strong>{{ schedulerStatus.poll_interval_sec }} s</strong></div>
          <div><span>工作线程</span><strong>{{ schedulerStatus.max_workers }}</strong></div>
          <div><span>执行中</span><strong>{{ schedulerStatus.inflight_tasks }}</strong></div>
          <div><span>活跃锁</span><strong>{{ schedulerStatus.active_lock_count }}</strong></div>
          <div><span>连续失败</span><strong>{{ schedulerStatus.consecutive_failures }}</strong></div>
        </div>
        <p v-if="schedulerStatus?.lock_observation_error" class="muted">锁扫描异常：{{ schedulerStatus.lock_observation_error }}</p>
        <p v-if="schedulerStatus?.last_error" class="muted">最近错误：{{ schedulerStatus.last_error }}</p>
      </article>

      <article class="obs-card">
        <div class="obs-head">
          <strong>Redis 活跃锁</strong>
          <span class="muted">{{ schedulerLocks.length }} 条</span>
        </div>
        <div v-if="schedulerLocks.length === 0" class="empty-inline">当前无活跃实例锁</div>
        <div v-else class="lock-list">
          <div v-for="item in schedulerLocks" :key="item.key" class="lock-row">
            <div><span>实例</span><strong>{{ item.instance_id ?? '-' }}</strong></div>
            <div><span>TTL</span><strong>{{ formatTtl(item.ttl_sec) }}</strong></div>
            <div class="wide"><span>Key</span><strong>{{ item.key }}</strong></div>
          </div>
        </div>
      </article>

      <article class="obs-card obs-card-wide">
        <div class="obs-head">
          <strong>最近调度 / 锁 / 连接器事件</strong>
          <span class="muted">{{ auditEvents.length }} 条</span>
        </div>
        <div v-if="auditEvents.length === 0" class="empty-inline">暂无相关审计事件</div>
        <div v-else class="audit-list">
          <div v-for="item in auditEvents" :key="item.id" class="audit-row">
            <div class="audit-meta">
              <strong>{{ item.event_type }}</strong>
              <span>{{ item.target_type }} / {{ item.target_id }}</span>
              <span>{{ formatTime(item.created_at) }}</span>
            </div>
            <p class="muted">{{ auditSummary(item) }}</p>
          </div>
        </div>
      </article>
    </section>

    <form class="run-filter-form" @submit.prevent="loadRuns">
      <label>
        包名
        <select v-model="packageFilter" :disabled="optionsLoading">
          <option value="">全部</option>
          <option v-for="item in packages" :key="item.id" :value="item.name">
            {{ item.name }}
          </option>
        </select>
      </label>

      <label>
        实例
        <select v-model="instanceFilter" :disabled="optionsLoading">
          <option value="">全部</option>
          <option v-for="item in instances" :key="item.id" :value="String(item.id)">
            {{ item.name }} (#{{ item.id }})
          </option>
        </select>
      </label>

      <label>
        状态
        <select v-model="statusFilter">
          <option value="">全部</option>
          <option v-for="item in statusOptions" :key="item" :value="item">
            {{ item }}
          </option>
        </select>
      </label>

      <label class="wide-field">
        关键字
        <input
          v-model="keywordFilter"
          type="text"
          placeholder="可搜索 run_id / package / version / trigger / environment / instance"
        />
      </label>

      <div class="run-filter-actions">
        <button type="submit" :disabled="loading">查询</button>
        <button type="button" class="secondary-button" @click="resetFilters" :disabled="loading">
          重置
        </button>
      </div>
    </form>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="loading" class="muted">正在加载运行记录。</p>

    <div v-if="!loading && filteredRuns.length === 0" class="empty-state">
      <h3>暂无运行记录</h3>
      <p>调整筛选条件，或先执行一次插件 / 实例运行。</p>
    </div>

    <div v-else class="run-layout">
      <div class="run-table-card">
        <div class="run-table-meta">
          <strong>查询结果</strong>
          <span class="muted">共 {{ filteredRuns.length }} 条 · 每页 {{ PAGE_SIZE }} 条</span>
        </div>

        <div class="table-wrapper">
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
                :class="{ active: run.run_id === selectedRunId }"
                @click="selectRun(run.run_id)"
              >
                <td><code>{{ run.run_id }}</code></td>
                <td>{{ run.package_name }}</td>
                <td>{{ run.version }}</td>
                <td>{{ instanceLabel(run) }}</td>
                <td>{{ run.trigger_type }}</td>
                <td><span class="status-chip">{{ run.status }}</span></td>
                <td>{{ formatTime(run.started_at) }}</td>
                <td>{{ formatDuration(run.started_at, run.finished_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="pagination-bar" v-if="filteredRuns.length > PAGE_SIZE">
          <button type="button" class="secondary-button" @click="goToPage(currentPage - 1)" :disabled="currentPage <= 1">
            上一页
          </button>
          <span class="muted">第 {{ currentPage }} / {{ totalPages }} 页</span>
          <button type="button" class="secondary-button" @click="goToPage(currentPage + 1)" :disabled="currentPage >= totalPages">
            下一页
          </button>
        </div>
      </div>

      <aside class="run-detail-card" v-if="selectedRun">
        <div class="run-detail-head">
          <div>
            <p class="eyebrow">{{ selectedRun.run_id }}</p>
            <h3>{{ selectedRun.package_name }} @ {{ selectedRun.version }}</h3>
            <p>
              {{ selectedRun.trigger_type }} · {{ selectedRun.environment }} · attempt {{ selectedRun.attempt }}
            </p>
          </div>
          <span class="status-chip">{{ selectedRun.status }}</span>
        </div>

        <div class="detail-tabs">
          <button type="button" class="detail-tab" :class="{ active: detailTab === 'overview' }" @click="detailTab = 'overview'">概览</button>
          <button type="button" class="detail-tab" :class="{ active: detailTab === 'inputs' }" @click="detailTab = 'inputs'">Inputs</button>
          <button type="button" class="detail-tab" :class="{ active: detailTab === 'outputs' }" @click="detailTab = 'outputs'">Outputs</button>
          <button type="button" class="detail-tab" :class="{ active: detailTab === 'metrics' }" @click="detailTab = 'metrics'">Metrics</button>
          <button type="button" class="detail-tab" :class="{ active: detailTab === 'error' }" @click="detailTab = 'error'">Error</button>
          <button type="button" class="detail-tab" :class="{ active: detailTab === 'logs' }" @click="detailTab = 'logs'">Logs</button>
          <button type="button" class="detail-tab" :class="{ active: detailTab === 'writeback' }" @click="detailTab = 'writeback'">Writeback</button>
        </div>

        <p v-if="detailError" class="error">{{ detailError }}</p>
        <p v-if="detailLoading" class="muted">正在加载详情。</p>

        <div v-if="detailTab === 'overview'" class="detail-panel">
          <div class="status-grid">
            <div><span>实例 ID</span><strong>{{ instanceLabel(selectedRun) }}</strong></div>
            <div><span>状态</span><strong>{{ selectedRun.status }}</strong></div>
            <div><span>开始时间</span><strong>{{ formatTime(selectedRun.started_at) }}</strong></div>
            <div><span>结束时间</span><strong>{{ formatTime(selectedRun.finished_at) }}</strong></div>
            <div><span>环境</span><strong>{{ selectedRun.environment }}</strong></div>
            <div><span>耗时</span><strong>{{ formatDuration(selectedRun.started_at, selectedRun.finished_at) }}</strong></div>
          </div>
        </div>

        <div v-else-if="detailTab === 'inputs'" class="detail-panel"><pre class="detail-pre">{{ stringify(selectedRun.inputs) }}</pre></div>
        <div v-else-if="detailTab === 'outputs'" class="detail-panel"><pre class="detail-pre">{{ stringify(selectedRun.outputs) }}</pre></div>
        <div v-else-if="detailTab === 'metrics'" class="detail-panel"><pre class="detail-pre">{{ stringify(selectedRun.metrics) }}</pre></div>
        <div v-else-if="detailTab === 'error'" class="detail-panel"><pre class="detail-pre">{{ stringify(selectedRun.error) }}</pre></div>

        <div v-else-if="detailTab === 'logs'" class="detail-panel">
          <div v-if="logs.length === 0" class="empty-inline">暂无日志</div>
          <div v-else class="log-list">
            <div v-for="item in logs" :key="item.id" class="log-row">
              <div class="log-meta">
                <strong>{{ item.level }}</strong>
                <span>{{ item.source }}</span>
                <span>{{ formatTime(item.created_at) }}</span>
              </div>
              <pre class="detail-pre compact">{{ item.message }}</pre>
            </div>
          </div>
        </div>

        <div v-else-if="detailTab === 'writeback'" class="detail-panel">
          <div v-if="writebacks.length === 0" class="empty-inline">暂无写回记录</div>
          <div v-else class="writeback-list">
            <div v-for="item in writebacks" :key="item.id" class="writeback-row">
              <div class="writeback-head">
                <strong>{{ item.output_name }}</strong>
                <span class="status-chip">{{ item.status }}</span>
              </div>
              <div class="writeback-grid">
                <div><span>目标数据源</span><strong>#{{ item.data_source_id }}</strong></div>
                <div><span>目标标签</span><strong>{{ item.target_tag }}</strong></div>
                <div><span>Dry Run</span><strong>{{ item.dry_run ? 'Yes' : 'No' }}</strong></div>
                <div><span>时间</span><strong>{{ formatTime(item.created_at) }}</strong></div>
              </div>
              <pre class="detail-pre compact">{{ stringify(item.value) }}</pre>
              <p v-if="item.reason" class="muted">原因：{{ item.reason }}</p>
            </div>
          </div>
        </div>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.run-page { max-width: 1360px; }
.observability-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin: 20px 0; }
.obs-card { padding: 18px; background: #ffffff; border: 1px solid #d8e3df; border-radius: 8px; display: grid; gap: 12px; }
.obs-card-wide { grid-column: 1 / -1; }
.obs-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.lock-list, .audit-list { display: grid; gap: 10px; }
.lock-row, .audit-row { display: grid; gap: 8px; padding: 12px; background: #fbfdfc; border: 1px solid #d8e3df; border-radius: 8px; }
.lock-row { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.lock-row .wide { grid-column: 1 / -1; }
.lock-row span, .audit-meta span { color: #5e6f6c; font-size: 13px; }
.audit-meta { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.run-filter-form { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; padding: 20px; background: #ffffff; border: 1px solid #d8e3df; border-radius: 8px; }
.run-filter-form label { display: grid; gap: 8px; color: #2f403d; font-weight: 600; }
.run-filter-form input, .run-filter-form select { width: 100%; padding: 10px; border: 1px solid #bacac5; border-radius: 6px; }
.run-filter-actions { display: flex; align-items: flex-end; gap: 10px; }
.run-layout { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(360px, 0.9fr); gap: 20px; margin-top: 20px; }
.run-table-card, .run-detail-card { padding: 20px; background: #ffffff; border: 1px solid #d8e3df; border-radius: 8px; }
.run-table-meta { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
.table-wrapper { overflow: auto; }
.runs-table { width: 100%; border-collapse: collapse; min-width: 900px; }
.runs-table th, .runs-table td { padding: 12px 10px; border-bottom: 1px solid #e4ece9; text-align: left; vertical-align: top; }
.runs-table thead th { color: #5e6f6c; font-size: 13px; font-weight: 700; background: #f7faf9; position: sticky; top: 0; }
.run-table-row { cursor: pointer; }
.run-table-row:hover { background: #f7faf9; }
.run-table-row.active { background: #edf5f2; }
.status-chip { display: inline-flex; align-items: center; justify-content: center; min-height: 28px; padding: 4px 8px; color: #2f403d; background: #edf5f2; border: 1px solid #d8e3df; border-radius: 999px; font-size: 12px; font-weight: 700; }
.pagination-bar { display: flex; align-items: center; justify-content: flex-end; gap: 10px; margin-top: 14px; }
.run-detail-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
.run-detail-head p:last-child { margin-bottom: 0; color: #41524f; }
.detail-tabs { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
.detail-tab { min-height: 34px; padding: 0 12px; color: #12685f; background: #ffffff; border: 1px solid #9db8b1; border-radius: 6px; font-weight: 700; }
.detail-tab.active { color: #ffffff; background: #12685f; border-color: #12685f; }
.detail-panel { display: grid; gap: 12px; }
.detail-pre { max-width: 100%; margin: 0; padding: 12px; overflow: auto; color: #172126; background: #f5f8f7; border: 1px solid #d8e3df; border-radius: 6px; }
.detail-pre.compact { max-height: 200px; }
.empty-inline { padding: 14px; color: #5e6f6c; background: #f7faf9; border: 1px dashed #c9d7d3; border-radius: 6px; }
.log-list, .writeback-list { display: grid; gap: 12px; }
.log-row, .writeback-row { display: grid; gap: 10px; padding: 12px; background: #fbfdfc; border: 1px solid #d8e3df; border-radius: 8px; }
.log-meta, .writeback-head { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.log-meta span { color: #5e6f6c; font-size: 13px; }
.writeback-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.writeback-grid div { display: grid; gap: 4px; padding: 10px; background: #f5f8f7; border: 1px solid #d8e3df; border-radius: 6px; }
.writeback-grid span { color: #5e6f6c; font-size: 13px; }
@media (max-width: 980px) {
  .observability-grid, .run-layout, .run-filter-form { grid-template-columns: 1fr; }
  .writeback-grid, .lock-row { grid-template-columns: 1fr; }
}
</style>
