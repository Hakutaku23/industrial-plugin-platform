<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getObservabilitySummary, type ObservabilitySummary, type ScheduleRunRecord } from '../api/observability'

const loading = ref(false)
const error = ref('')
const summary = ref<ObservabilitySummary | null>(null)

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    summary.value = await getObservabilitySummary()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '系统观测信息加载失败'
  } finally {
    loading.value = false
  }
}

const runtimeObservation = computed<Record<string, unknown>>(() => summary.value?.scheduler.runtime_observation ?? {})
const recentRuns = computed<ScheduleRunRecord[]>(() => summary.value?.recent_schedule_runs ?? [])
const recentEvents = computed(() => summary.value?.recent_events ?? [])
const lockItems = computed(() => summary.value?.locks ?? [])
const scheduleStats = computed(() => summary.value?.schedule_run_stats ?? {
  completed_24h: 0,
  failed_24h: 0,
  timed_out_24h: 0,
  skipped_24h: 0,
  partial_success_24h: 0,
})

function fmtTime(value: unknown) {
  if (!value) return '-'
  const text = String(value)
  const parsed = new Date(text)
  return Number.isNaN(parsed.getTime()) ? text : parsed.toLocaleString()
}

function fmtDurationSec(value: unknown) {
  const num = Number(value)
  if (Number.isNaN(num)) return '-'
  if (num < 1000) return `${num} ms`
  return `${(num / 1000).toFixed(2)} s`
}

function fmtLockTtl(value: number | null | undefined) {
  if (value == null) return '-'
  return `${value.toFixed(1)} s`
}

function metricOf(run: ScheduleRunRecord, key: string) {
  return run.metrics?.[key]
}

function eventMessage(details: Record<string, unknown>) {
  const message = details?.message
  if (typeof message === 'string' && message) return message
  const skipped = details?.skipped_slots
  if (Array.isArray(skipped) && skipped.length > 0) return `skipped slots: ${skipped.join(', ')}`
  return '-'
}

onMounted(refresh)
</script>

<template>
  <section class="obs-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">System Observability</p>
        <h1>系统观测中心</h1>
        <p class="subtitle">集中查看调度器、授权状态、活跃锁与最近定时运行结果，便于工厂试运行前排障与验收。</p>
      </div>
      <button class="primary" @click="refresh" :disabled="loading">{{ loading ? '刷新中…' : '刷新状态' }}</button>
    </header>

    <p v-if="error" class="banner error">{{ error }}</p>

    <div v-if="summary" class="grid">
      <article class="card">
        <h2>调度器状态</h2>
        <div class="kv-grid">
          <div><span>模式</span><strong>{{ summary.scheduler.mode }}</strong></div>
          <div><span>活跃</span><strong>{{ summary.scheduler.thread_alive ? 'Yes' : 'No' }}</strong></div>
          <div><span>Daemon PID</span><strong>{{ summary.scheduler.daemon_pid ?? '-' }}</strong></div>
          <div><span>Exit Code</span><strong>{{ summary.scheduler.daemon_exit_code ?? '-' }}</strong></div>
          <div><span>Worker ID</span><strong class="mono">{{ summary.scheduler.worker_id }}</strong></div>
          <div><span>已运行</span><strong>{{ summary.scheduler.started_age_sec ?? 0 }} s</strong></div>
          <div class="wide"><span>二进制路径</span><strong class="mono">{{ summary.scheduler.daemon_binary_path || '-' }}</strong></div>
          <div class="wide"><span>最近错误</span><strong>{{ summary.scheduler.last_error || '-' }}</strong></div>
        </div>
      </article>

      <article class="card">
        <h2>授权状态</h2>
        <div class="kv-grid">
          <div><span>状态</span><strong>{{ summary.license.status }}</strong></div>
          <div><span>有效</span><strong>{{ summary.license.valid ? 'Yes' : 'No' }}</strong></div>
          <div><span>只读</span><strong>{{ summary.license.readonly_mode ? 'Yes' : 'No' }}</strong></div>
          <div><span>授权类型</span><strong>{{ summary.license.grant_mode || '-' }}</strong></div>
          <div><span>客户</span><strong>{{ summary.license.customer_name || '-' }}</strong></div>
          <div><span>许可证 ID</span><strong class="mono">{{ summary.license.license_id || '-' }}</strong></div>
          <div class="wide"><span>说明</span><strong>{{ summary.license.message }}</strong></div>
        </div>
      </article>

      <article class="card wide-card">
        <h2>调度运行统计（近 24h）</h2>
        <div class="stats-grid">
          <div class="stat-box success"><span>Completed</span><strong>{{ scheduleStats.completed_24h }}</strong></div>
          <div class="stat-box warn"><span>Partial</span><strong>{{ scheduleStats.partial_success_24h }}</strong></div>
          <div class="stat-box error"><span>Failed</span><strong>{{ scheduleStats.failed_24h }}</strong></div>
          <div class="stat-box timeout"><span>Timed Out</span><strong>{{ scheduleStats.timed_out_24h }}</strong></div>
          <div class="stat-box skipped"><span>Skipped</span><strong>{{ scheduleStats.skipped_24h }}</strong></div>
        </div>
      </article>

      <article class="card wide-card">
        <h2>运行时观测</h2>
        <div class="kv-grid">
          <div><span>Last Due Poll</span><strong>{{ fmtTime(runtimeObservation.last_due_poll_at) }}</strong></div>
          <div><span>Last Claim</span><strong>{{ fmtTime(runtimeObservation.last_claim_at) }}</strong></div>
          <div><span>Last Execute</span><strong>{{ fmtTime(runtimeObservation.last_execute_at) }}</strong></div>
          <div><span>Last Complete</span><strong>{{ fmtTime(runtimeObservation.last_complete_at) }}</strong></div>
          <div><span>Due Poll Count</span><strong>{{ runtimeObservation.due_poll_count ?? 0 }}</strong></div>
          <div><span>Claim Count</span><strong>{{ runtimeObservation.claim_count ?? 0 }}</strong></div>
          <div><span>Execute Count</span><strong>{{ runtimeObservation.execute_count ?? 0 }}</strong></div>
          <div><span>Complete Count</span><strong>{{ runtimeObservation.complete_count ?? 0 }}</strong></div>
          <div><span>Last Due Count</span><strong>{{ runtimeObservation.last_due_count ?? 0 }}</strong></div>
          <div><span>Next Due In</span><strong>{{ runtimeObservation.last_next_due_in_ms ?? '-' }} ms</strong></div>
          <div><span>Suggested Poll</span><strong>{{ runtimeObservation.last_suggested_poll_interval_ms ?? '-' }} ms</strong></div>
          <div><span>Last Scheduled For</span><strong>{{ fmtTime(runtimeObservation.last_scheduled_for) }}</strong></div>
          <div><span>Last Claimed At</span><strong>{{ fmtTime(runtimeObservation.last_claimed_at) }}</strong></div>
          <div><span>Last Run Start</span><strong>{{ fmtTime(runtimeObservation.last_run_started_at) }}</strong></div>
          <div><span>Last Run Finish</span><strong>{{ fmtTime(runtimeObservation.last_run_finished_at) }}</strong></div>
          <div class="wide"><span>Runtime Error</span><strong>{{ runtimeObservation.last_error ?? '-' }}</strong></div>
        </div>
      </article>

      <article class="card wide-card">
        <h2>活跃锁</h2>
        <div v-if="lockItems.length === 0" class="empty">当前无活跃锁</div>
        <div v-else class="table-wrap">
          <table>
            <thead>
              <tr><th>实例</th><th>TTL</th><th>Key</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in lockItems" :key="item.key">
                <td>{{ item.instance_id ?? '-' }}</td>
                <td>{{ fmtLockTtl(item.ttl_sec) }}</td>
                <td class="mono">{{ item.key }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <article class="card wide-card">
        <h2>最近定时运行</h2>
        <div v-if="recentRuns.length === 0" class="empty">暂无定时运行记录</div>
        <div v-else class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Run ID</th>
                <th>实例</th>
                <th>状态</th>
                <th>开始时间</th>
                <th>耗时</th>
                <th>计划时间</th>
                <th>漂移</th>
                <th>跳过原因</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="run in recentRuns.slice(0, 20)" :key="run.run_id">
                <td class="mono">{{ run.run_id }}</td>
                <td>{{ run.instance_id ?? '-' }}</td>
                <td>{{ run.status }}</td>
                <td>{{ fmtTime(run.started_at) }}</td>
                <td>{{ fmtDurationSec(metricOf(run, 'execution_wall_time_ms')) }}</td>
                <td>{{ fmtTime(metricOf(run, 'scheduled_for')) }}</td>
                <td>{{ metricOf(run, 'drift_ms') ?? '-' }} ms</td>
                <td>{{ run.error?.message || '-' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <article class="card wide-card">
        <h2>最近事件</h2>
        <div v-if="recentEvents.length === 0" class="empty">暂无相关事件</div>
        <div v-else class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>时间</th>
                <th>事件</th>
                <th>目标</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in recentEvents" :key="item.id">
                <td>{{ fmtTime(item.created_at) }}</td>
                <td>{{ item.event_type }}</td>
                <td>{{ item.target_type }} / {{ item.target_id }}</td>
                <td>{{ eventMessage(item.details) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.obs-page { display: grid; gap: 20px; }
.page-header { display: flex; justify-content: space-between; gap: 16px; align-items: flex-end; }
.page-header h1 { margin: 0; font-size: 28px; }
.eyebrow { margin: 0 0 6px; color: #64748b; font-size: 12px; text-transform: uppercase; }
.subtitle { color: #64748b; max-width: 920px; }
.primary { min-height: 40px; padding: 0 16px; border-radius: 8px; border: 1px solid #2563eb; background: #2563eb; color: #fff; cursor: pointer; }
.banner { margin: 0; padding: 12px 14px; border-radius: 8px; }
.banner.error { background: #fee2e2; color: #991b1b; }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.card { background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; }
.card h2 { margin-top: 0; }
.wide-card { grid-column: 1 / -1; }
.kv-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.kv-grid > div { display: grid; gap: 4px; padding: 12px; background: #f8fafc; border-radius: 8px; }
.kv-grid span { color: #64748b; font-size: 12px; }
.kv-grid strong { font-size: 14px; color: #0f172a; overflow-wrap: anywhere; }
.kv-grid .wide { grid-column: 1 / -1; }
.stats-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; }
.stat-box { padding: 14px; border-radius: 10px; display: grid; gap: 6px; }
.stat-box span { font-size: 12px; color: #475569; }
.stat-box strong { font-size: 24px; }
.stat-box.success { background: #dcfce7; color: #166534; }
.stat-box.warn { background: #fef3c7; color: #92400e; }
.stat-box.error { background: #fee2e2; color: #991b1b; }
.stat-box.timeout { background: #e0f2fe; color: #0c4a6e; }
.stat-box.skipped { background: #f1f5f9; color: #334155; }
.table-wrap { overflow: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 10px 12px; border-bottom: 1px solid #e2e8f0; text-align: left; vertical-align: top; }
th { background: #f8fafc; color: #475569; font-size: 12px; text-transform: uppercase; }
.empty { padding: 18px; background: #f8fafc; border-radius: 8px; color: #64748b; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; overflow-wrap: anywhere; }
@media (max-width: 1100px) {
  .grid, .stats-grid, .page-header { grid-template-columns: 1fr; display: grid; }
}
</style>
