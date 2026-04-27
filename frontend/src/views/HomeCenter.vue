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
  <section class="fui-obs-module">
    <div class="module-header">
      <div class="fui-title-box">
        <h2>系统状态</h2>
        <span>OBSERVABILITY</span>
      </div>
      <button class="fui-btn-glow" @click="refresh" :disabled="loading">
        {{ loading ? '同步中...' : '刷新状态' }}
      </button>
    </div>

    <p v-if="error" class="fui-alert error">{{ error }}</p>

    <div v-if="summary" class="fui-grid">
      <article class="fui-panel">
        <div class="panel-head">调度器核心状态</div>
        <div class="fui-kv">
          <div><span>模式</span><strong>{{ summary.scheduler.mode }}</strong></div>
          <div><span>线程活跃</span><strong :class="{ 'text-ok': summary.scheduler.thread_alive }">{{ summary.scheduler.thread_alive ? 'ONLINE' : 'OFFLINE' }}</strong></div>
          <div><span>Daemon PID</span><strong>{{ summary.scheduler.daemon_pid ?? '-' }}</strong></div>
          <div><span>Worker ID</span><strong class="fui-mono">{{ summary.scheduler.worker_id }}</strong></div>
          <div><span>运行时长</span><strong>{{ summary.scheduler.started_age_sec ?? 0 }} s</strong></div>
          <div><span>Exit Code</span><strong>{{ summary.scheduler.daemon_exit_code ?? '-' }}</strong></div>
          <div class="wide"><span>最近异常</span><strong class="text-err">{{ summary.scheduler.last_error || '无' }}</strong></div>
        </div>
      </article>

      <article class="fui-panel">
        <div class="panel-head">运行频率监控</div>
        <div class="fui-kv">
          <div><span>Due Poll 次数</span><strong>{{ runtimeObservation.due_poll_count ?? 0 }}</strong></div>
          <div><span>Claim 次数</span><strong>{{ runtimeObservation.claim_count ?? 0 }}</strong></div>
          <div><span>Execute 次数</span><strong>{{ runtimeObservation.execute_count ?? 0 }}</strong></div>
          <div><span>Complete 次数</span><strong>{{ runtimeObservation.complete_count ?? 0 }}</strong></div>
          <div><span>Last Due 延迟</span><strong>{{ runtimeObservation.last_next_due_in_ms ?? '-' }} ms</strong></div>
          <div><span>推荐轮询间隔</span><strong>{{ runtimeObservation.last_suggested_poll_interval_ms ?? '-' }} ms</strong></div>
          <div class="wide"><span>最后轮询时间</span><strong>{{ fmtTime(runtimeObservation.last_due_poll_at) }}</strong></div>
        </div>
      </article>

      <article class="fui-panel wide-panel">
        <div class="panel-head">分布式活跃锁 (Redis Locks)</div>
        <div v-if="lockItems.length === 0" class="fui-empty">当前环境无活跃死锁或占位锁</div>
        <div v-else class="fui-table-wrap">
          <table class="fui-table">
            <thead>
              <tr><th>关联实例</th><th>TTL (生存时间)</th><th>Key 标识</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in lockItems" :key="item.key">
                <td>{{ item.instance_id ?? '-' }}</td>
                <td class="text-warn">{{ fmtLockTtl(item.ttl_sec) }}</td>
                <td class="fui-mono">{{ item.key }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <article class="fui-panel wide-panel">
        <div class="panel-head">定时调度快照 (Recent Runs)</div>
        <div v-if="recentRuns.length === 0" class="fui-empty">暂无调度记录</div>
        <div v-else class="fui-table-wrap">
          <table class="fui-table">
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
              <tr v-for="run in recentRuns.slice(0, 10)" :key="run.run_id">
                <td class="fui-mono">{{ run.run_id.substring(0,8) }}...</td>
                <td>{{ run.instance_id ?? '-' }}</td>
                <td>
                  <span :class="['fui-badge', run.status.toLowerCase()]">{{ run.status }}</span>
                </td>
                <td>{{ fmtTime(run.started_at) }}</td>
                <td class="text-ok">{{ fmtDurationSec(metricOf(run, 'execution_wall_time_ms')) }}</td>
                <td>{{ metricOf(run, 'drift_ms') ?? '-' }} ms</td>
                <td class="text-err">{{ run.error?.message || '-' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
      
      <article class="fui-panel wide-panel">
        <div class="panel-head">系统关键事件轨迹</div>
        <div v-if="recentEvents.length === 0" class="fui-empty">暂无事件记录</div>
        <div v-else class="fui-table-wrap">
          <table class="fui-table">
            <thead>
              <tr><th>发生时间</th><th>事件类型</th><th>目标实体</th><th>详细说明</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in recentEvents" :key="item.id">
                <td>{{ fmtTime(item.created_at) }}</td>
                <td class="text-warn">{{ item.event_type }}</td>
                <td class="fui-mono">{{ item.target_type }} / {{ item.target_id.substring(0,8) }}</td>
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
.fui-obs-module { margin-top: 30px; }
.module-header { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 20px; border-bottom: 1px solid rgba(0, 243, 255, 0.2); padding-bottom: 10px; }
.fui-title-box h2 { margin: 0; color: #fff; font-size: 20px; letter-spacing: 1px; }
.fui-title-box span { color: #00f3ff; font-size: 12px; letter-spacing: 2px; }

.fui-btn-glow {
  background: rgba(0, 243, 255, 0.1);
  border: 1px solid #00f3ff;
  color: #00f3ff;
  padding: 8px 20px;
  cursor: pointer;
  box-shadow: 0 0 10px rgba(0, 243, 255, 0.2) inset;
  transition: 0.3s;
  clip-path: polygon(10px 0, 100% 0, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0 100%, 0 10px);
}
.fui-btn-glow:hover { background: rgba(0, 243, 255, 0.3); box-shadow: 0 0 20px rgba(0, 243, 255, 0.6) inset; }

.fui-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px; }
.wide-panel { grid-column: 1 / -1; }

.fui-panel {
  background: rgba(2, 18, 38, 0.7);
  border: 1px solid rgba(0, 162, 255, 0.3);
  box-shadow: inset 0 0 20px rgba(0, 162, 255, 0.1);
  position: relative;
  padding: 20px;
}
/* 科技感四个角 */
.fui-panel::before, .fui-panel::after {
  content: ''; position: absolute; width: 15px; height: 15px; border: 2px solid transparent;
}
.fui-panel::before { top: -1px; left: -1px; border-top-color: #00f3ff; border-left-color: #00f3ff; }
.fui-panel::after { bottom: -1px; right: -1px; border-bottom-color: #00f3ff; border-right-color: #00f3ff; }

.panel-head {
  background: linear-gradient(90deg, rgba(0, 243, 255, 0.2) 0%, transparent 100%);
  border-left: 4px solid #00f3ff;
  padding: 6px 12px;
  color: #fff;
  font-size: 16px;
  font-weight: bold;
  margin-bottom: 16px;
}

.fui-kv { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.fui-kv > div { padding: 10px; background: rgba(0, 0, 0, 0.3); border: 1px solid rgba(0, 243, 255, 0.1); display: grid; gap: 4px; }
.fui-kv .wide { grid-column: 1 / -1; }
.fui-kv span { color: #a0cfff; font-size: 12px; }
.fui-kv strong { color: #fff; font-size: 14px; word-break: break-all; }

.fui-table-wrap { overflow-x: auto; }
.fui-table { width: 100%; border-collapse: collapse; }
.fui-table th { background: rgba(0, 243, 255, 0.1); color: #00f3ff; padding: 12px; text-align: left; font-size: 13px; border-bottom: 1px solid #00f3ff; }
.fui-table td { padding: 12px; color: #d0e8ff; border-bottom: 1px solid rgba(0, 243, 255, 0.1); font-size: 13px; }
.fui-table tr:hover td { background: rgba(0, 243, 255, 0.05); }

.fui-empty { padding: 20px; text-align: center; color: #a0cfff; font-style: italic; background: rgba(0, 0, 0, 0.2); }
.fui-mono { font-family: "JetBrains Mono", Consolas, monospace; color: #a0cfff; }

.text-ok { color: #00ffaa !important; text-shadow: 0 0 5px #00ffaa; }
.text-warn { color: #ffbb00 !important; }
.text-err { color: #ff4444 !important; }

.fui-badge { padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }
.fui-badge.completed { background: rgba(0, 255, 170, 0.2); border: 1px solid #00ffaa; color: #00ffaa; }
.fui-badge.failed { background: rgba(255, 68, 68, 0.2); border: 1px solid #ff4444; color: #ff4444; }
.fui-badge.running { background: rgba(0, 243, 255, 0.2); border: 1px solid #00f3ff; color: #00f3ff; }
</style>