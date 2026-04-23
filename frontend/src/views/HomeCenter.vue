<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { listInstances, listPackages, listRuns } from '../api/packages'
import { getObservabilitySummary, type ObservabilitySummary } from '../api/observability'

const loading = ref(false)
const error = ref('')
const summary = ref<ObservabilitySummary | null>(null)
const packageCount = ref(0)
const instanceCount = ref(0)
const totalRunCount = ref(0)

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const [obs, packages, instances, runs] = await Promise.all([
      getObservabilitySummary(),
      listPackages(),
      listInstances(),
      listRuns(),
    ])
    summary.value = obs
    packageCount.value = packages.length
    instanceCount.value = instances.length
    totalRunCount.value = runs.length
  } catch (err) {
    error.value = err instanceof Error ? err.message : '首页信息加载失败'
  } finally {
    loading.value = false
  }
}

const scheduleStats = computed(() => summary.value?.schedule_run_stats ?? {
  completed_24h: 0,
  failed_24h: 0,
  timed_out_24h: 0,
  skipped_24h: 0,
  partial_success_24h: 0,
})

const scheduler = computed(() => summary.value?.scheduler)
const license = computed(() => summary.value?.license)
const lockCount = computed(() => summary.value?.locks?.length ?? 0)
const recentEvents = computed(() => summary.value?.recent_events?.slice(0, 6) ?? [])

function fmtTime(value: string | null | undefined) {
  if (!value) return '-'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

onMounted(refresh)
</script>

<template>
  <section class="home-page">
    <header class="hero">
      <div>
        <p class="eyebrow">Industrial Algorithm Operations Center</p>
        <h1>工业智能算法运行与管控平台</h1>
        <p class="subtitle">面向工厂试运行的一体化算法资产、调度执行、授权治理与运行观测中台。</p>
      </div>
      <div class="hero-actions">
        <button class="primary" @click="refresh" :disabled="loading">{{ loading ? '刷新中…' : '刷新看板' }}</button>
        <RouterLink class="secondary-link" to="/system/observability">进入系统观测</RouterLink>
      </div>
    </header>

    <p v-if="error" class="banner error">{{ error }}</p>

    <section class="dashboard-grid">
      <article class="metric-card">
        <span>算法资产</span>
        <strong>{{ packageCount }}</strong>
        <small>已登记插件包总数</small>
      </article>
      <article class="metric-card">
        <span>实例编排</span>
        <strong>{{ instanceCount }}</strong>
        <small>当前实例配置总数</small>
      </article>
      <article class="metric-card">
        <span>运行记录</span>
        <strong>{{ totalRunCount }}</strong>
        <small>平台运行记录累计数</small>
      </article>
      <article class="metric-card">
        <span>活跃锁</span>
        <strong>{{ lockCount }}</strong>
        <small>当前 Redis 实例锁数量</small>
      </article>
      <article class="metric-card status" :class="license?.valid ? 'ok' : 'warn'">
        <span>许可证状态</span>
        <strong>{{ license?.status || '-' }}</strong>
        <small>{{ license?.message || '未加载授权状态' }}</small>
      </article>
      <article class="metric-card status" :class="scheduler?.thread_alive ? 'ok' : 'warn'">
        <span>调度器状态</span>
        <strong>{{ scheduler?.thread_alive ? 'ONLINE' : 'OFFLINE' }}</strong>
        <small>模式：{{ scheduler?.mode || '-' }}</small>
      </article>
    </section>

    <section class="panel-grid">
      <article class="card wide-card">
        <div class="card-head">
          <h2>运行看板</h2>
          <span>近 24h</span>
        </div>
        <div class="stats-grid">
          <div class="stat success"><span>Completed</span><strong>{{ scheduleStats.completed_24h }}</strong></div>
          <div class="stat warn"><span>Partial</span><strong>{{ scheduleStats.partial_success_24h }}</strong></div>
          <div class="stat error"><span>Failed</span><strong>{{ scheduleStats.failed_24h }}</strong></div>
          <div class="stat timeout"><span>Timed Out</span><strong>{{ scheduleStats.timed_out_24h }}</strong></div>
          <div class="stat skipped"><span>Skipped</span><strong>{{ scheduleStats.skipped_24h }}</strong></div>
        </div>
      </article>

      <article class="card wide-card">
        <div class="card-head">
          <h2>业务中台入口</h2>
          <span>按场景进入</span>
        </div>
        <div class="center-grid">
          <RouterLink class="center-card" to="/packages/upload">
            <strong>算法上传中心</strong>
            <p>上传、更新、校验插件包。</p>
          </RouterLink>
          <RouterLink class="center-card" to="/packages">
            <strong>算法资产中心</strong>
            <p>查看插件版本、摘要与资产清单。</p>
          </RouterLink>
          <RouterLink class="center-card" to="/data-sources">
            <strong>数据接入中心</strong>
            <p>管理数据源连接与读写开关。</p>
          </RouterLink>
          <RouterLink class="center-card" to="/instances">
            <strong>实例编排中心</strong>
            <p>配置输入输出绑定、参数与定时计划。</p>
          </RouterLink>
          <RouterLink class="center-card" to="/runs">
            <strong>运行监管中心</strong>
            <p>查看运行状态、日志、写回与异常。</p>
          </RouterLink>
          <RouterLink class="center-card" to="/system/observability">
            <strong>系统观测中心</strong>
            <p>查看调度器、锁、授权与近 24h 运行统计。</p>
          </RouterLink>
        </div>
      </article>

      <article class="card">
        <div class="card-head">
          <h2>调度与授权摘要</h2>
          <span>系统关键状态</span>
        </div>
        <div class="kv-grid">
          <div><span>调度模式</span><strong>{{ scheduler?.mode || '-' }}</strong></div>
          <div><span>Daemon PID</span><strong>{{ scheduler?.daemon_pid ?? '-' }}</strong></div>
          <div><span>最后错误</span><strong>{{ scheduler?.last_error || '-' }}</strong></div>
          <div><span>授权类型</span><strong>{{ license?.grant_mode || '-' }}</strong></div>
          <div><span>客户</span><strong>{{ license?.customer_name || '-' }}</strong></div>
          <div><span>许可证 ID</span><strong>{{ license?.license_id || '-' }}</strong></div>
        </div>
      </article>

      <article class="card">
        <div class="card-head">
          <h2>最近关键事件</h2>
          <span>最新 6 条</span>
        </div>
        <div v-if="recentEvents.length === 0" class="empty">暂无关键事件</div>
        <div v-else class="event-list">
          <div v-for="item in recentEvents" :key="item.id" class="event-item">
            <strong>{{ item.event_type }}</strong>
            <span>{{ fmtTime(item.created_at) }}</span>
            <p>{{ item.target_type }} / {{ item.target_id }}</p>
          </div>
        </div>
      </article>
    </section>
  </section>
</template>

<style scoped>
.home-page { display: grid; gap: 20px; }
.hero { display: flex; justify-content: space-between; gap: 20px; align-items: flex-end; background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: #fff; border-radius: 18px; padding: 28px 32px; }
.eyebrow { margin: 0 0 8px; color: #93c5fd; font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }
.hero h1 { margin: 0 0 10px; font-size: 32px; }
.subtitle { margin: 0; color: #cbd5e1; max-width: 760px; }
.hero-actions { display: flex; gap: 12px; align-items: center; }
.primary, .secondary-link { min-height: 40px; padding: 0 16px; border-radius: 8px; border: 1px solid transparent; display: inline-flex; align-items: center; justify-content: center; text-decoration: none; cursor: pointer; }
.primary { background: #2563eb; color: #fff; border-color: #2563eb; }
.secondary-link { background: rgba(255,255,255,0.08); color: #fff; border-color: rgba(255,255,255,0.14); }
.banner.error { background: #fee2e2; color: #991b1b; padding: 12px 14px; border-radius: 8px; }
.dashboard-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 16px; }
.metric-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 14px; padding: 18px; display: grid; gap: 8px; }
.metric-card span { color: #64748b; font-size: 13px; }
.metric-card strong { font-size: 28px; color: #0f172a; }
.metric-card small { color: #64748b; }
.metric-card.status.ok { background: #f0fdf4; }
.metric-card.status.warn { background: #fff7ed; }
.panel-grid { display: grid; grid-template-columns: 1.35fr 1fr; gap: 20px; }
.card { background: #fff; border: 1px solid #e2e8f0; border-radius: 14px; padding: 20px; }
.wide-card { grid-column: 1 / -1; }
.card-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.card-head h2 { margin: 0; font-size: 18px; }
.card-head span { color: #64748b; font-size: 13px; }
.stats-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; }
.stat { padding: 14px; border-radius: 10px; display: grid; gap: 6px; }
.stat span { font-size: 12px; color: #475569; }
.stat strong { font-size: 24px; }
.stat.success { background: #dcfce7; color: #166534; }
.stat.warn { background: #fef3c7; color: #92400e; }
.stat.error { background: #fee2e2; color: #991b1b; }
.stat.timeout { background: #e0f2fe; color: #0c4a6e; }
.stat.skipped { background: #f1f5f9; color: #334155; }
.center-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.center-card { display: grid; gap: 8px; padding: 18px; border: 1px solid #dbeafe; border-radius: 12px; text-decoration: none; color: inherit; background: #f8fbff; }
.center-card:hover { border-color: #93c5fd; background: #eff6ff; }
.center-card strong { color: #0f172a; }
.center-card p { margin: 0; color: #64748b; font-size: 14px; }
.kv-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.kv-grid > div { display: grid; gap: 4px; padding: 12px; background: #f8fafc; border-radius: 8px; }
.kv-grid span { color: #64748b; font-size: 12px; }
.kv-grid strong { color: #0f172a; font-size: 14px; overflow-wrap: anywhere; }
.event-list { display: grid; gap: 12px; }
.event-item { padding: 14px; background: #f8fafc; border-radius: 10px; display: grid; gap: 6px; }
.event-item strong { color: #0f172a; }
.event-item span, .event-item p { color: #64748b; margin: 0; }
.empty { padding: 18px; background: #f8fafc; border-radius: 8px; color: #64748b; }
@media (max-width: 1200px) {
  .dashboard-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .center-grid, .stats-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .panel-grid { grid-template-columns: 1fr; }
}
@media (max-width: 900px) {
  .hero, .hero-actions { display: grid; }
  .dashboard-grid, .center-grid, .stats-grid, .kv-grid { grid-template-columns: 1fr; }
}
</style>
