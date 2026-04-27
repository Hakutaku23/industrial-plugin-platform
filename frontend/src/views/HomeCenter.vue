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
    error.value = err instanceof Error ? err.message : '系统状态加载失败'
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
  if (Array.isArray(skipped) && skipped.length > 0) return `跳过的时段: ${skipped.join(', ')}`
  return '-'
}

// 新增：将后端的英文状态转换为友好的中文
function formatStatus(status: string) {
  const s = status.toLowerCase()
  if (s === 'running') return '运行中'
  if (s === 'completed' || s === 'success') return '已完成'
  if (s === 'failed' || s === 'error') return '已失败'
  return status
}

onMounted(refresh)
</script>

<template>
  <section class="screen-wrapper">
    <!-- 顶部标题与控制区 -->
    <header class="screen-header">
      <div class="header-left-dec"></div>
      <div class="header-title">
        <h2>系统总状态</h2>
        <span>运行监控看板</span>
      </div>
      <div class="header-right-ctrl">
        <button class="fui-btn-glow" @click="refresh" :disabled="loading">
          <span class="icon">⟳</span> {{ loading ? '状态加载中...' : '实时刷新' }}
        </button>
      </div>
    </header>

    <p v-if="error" class="fui-alert error">{{ error }}</p>

    <div v-if="summary" class="screen-body">
      <!-- 核心 KPI 概览区 -->
      <div class="kpi-row">
        <div class="kpi-card">
          <div class="kpi-label">核心调度状态</div>
          <div class="kpi-value" :class="summary.scheduler.thread_alive ? 'text-ok text-pulse' : 'text-err'">
            {{ summary.scheduler.thread_alive ? '运行中' : '已离线' }}
          </div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">已连续运行</div>
          <div class="kpi-value text-cyan">{{ summary.scheduler.started_age_sec ?? 0 }}<span class="unit">秒</span></div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">累计分配任务数</div>
          <div class="kpi-value text-cyan">{{ runtimeObservation.claim_count ?? 0 }}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">成功执行任务数</div>
          <div class="kpi-value text-cyan">{{ runtimeObservation.execute_count ?? 0 }}</div>
        </div>
      </div>

      <!-- 三列大屏主体布局 -->
      <div class="dashboard-grid">
        
        <!-- 左侧区域：基础架构态势 -->
        <div class="ds-col side-col">
          <article class="fui-panel">
            <div class="panel-head">
              <span class="bracket">[</span> 基础运行信息 <span class="bracket">]</span>
            </div>
            <ul class="tech-list">
              <li><span>运行模式</span><strong class="text-warn">{{ summary.scheduler.mode }}</strong></li>
              <li><span>系统进程编号</span><strong class="fui-mono">{{ summary.scheduler.daemon_pid ?? '-' }}</strong></li>
              <li><span>工作节点标识</span><strong class="fui-mono text-cyan">{{ summary.scheduler.worker_id }}</strong></li>
              <li><span>上次退出状态</span><strong>{{ summary.scheduler.daemon_exit_code ?? '正常' }}</strong></li>
              <li class="col-span-full" v-if="summary.scheduler.last_error">
                <span>近期异常报错</span><strong class="text-err">{{ summary.scheduler.last_error }}</strong>
              </li>
            </ul>
          </article>

          <article class="fui-panel flex-fill">
            <div class="panel-head">
              <span class="bracket">[</span> 集群任务锁状态 <span class="bracket">]</span>
            </div>
            <div v-if="lockItems.length === 0" class="fui-empty data-safe">
              <span class="safe-icon">✓</span> 当前无排队或冲突任务
            </div>
            <div v-else class="fui-table-wrap scroll-y">
              <table class="fui-table density-high">
                <thead>
                  <tr><th>锁定标识</th><th>占用节点</th><th>剩余时间</th></tr>
                </thead>
                <tbody>
                  <tr v-for="item in lockItems" :key="item.key">
                    <td class="fui-mono text-cyan">{{ item.key }}</td>
                    <td>{{ item.instance_id ?? '-' }}</td>
                    <td class="text-warn">{{ fmtLockTtl(item.ttl_sec) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </article>
        </div>

        <!-- 中间区域：核心业务流 -->
        <div class="ds-col center-col">
          <article class="fui-panel main-panel flex-fill">
            <div class="panel-head center-head">
              <div class="head-glow"></div>
              <span>实时任务执行流水</span>
            </div>
            <div v-if="recentRuns.length === 0" class="fui-empty">暂无任务执行记录</div>
            <div v-else class="fui-table-wrap scroll-y">
              <table class="fui-table main-table">
                <thead>
                  <tr>
                    <th>任务编号</th>
                    <th>执行节点</th>
                    <th>当前状态</th>
                    <th>开始时间</th>
                    <th>执行耗时</th>
                    <th>时间误差</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="run in recentRuns.slice(0, 15)" :key="run.run_id">
                    <td class="fui-mono text-cyan">{{ run.run_id.substring(0,8) }}</td>
                    <td class="fui-mono">{{ run.instance_id ?? '-' }}</td>
                    <td>
                      <!-- class保持原始英文对应CSS，展示用中文 -->
                      <span :class="['fui-badge', run.status.toLowerCase()]">
                        <i class="dot"></i>{{ formatStatus(run.status) }}
                      </span>
                    </td>
                    <td>{{ fmtTime(run.started_at) }}</td>
                    <td class="text-ok font-num">{{ fmtDurationSec(metricOf(run, 'execution_wall_time_ms')) }}</td>
                    <td class="font-num text-warn">{{ metricOf(run, 'drift_ms') ?? '-' }} ms</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </article>
        </div>

        <!-- 右侧区域：频次与事件感知 -->
        <div class="ds-col side-col">
          <article class="fui-panel">
            <div class="panel-head">
              <span class="bracket">[</span> 调度频率监控 <span class="bracket">]</span>
            </div>
            <div class="grid-stats">
              <div class="stat-box">
                <span class="lbl">任务扫描次数</span>
                <span class="val">{{ runtimeObservation.due_poll_count ?? 0 }}</span>
              </div>
              <div class="stat-box">
                <span class="lbl">任务完成次数</span>
                <span class="val">{{ runtimeObservation.complete_count ?? 0 }}</span>
              </div>
              <div class="stat-box">
                <span class="lbl">最近任务延迟</span>
                <span class="val">{{ runtimeObservation.last_next_due_in_ms ?? '-' }} <small>ms</small></span>
              </div>
              <div class="stat-box">
                <span class="lbl">建议扫描间隔</span>
                <span class="val text-warn">{{ runtimeObservation.last_suggested_poll_interval_ms ?? '-' }} <small>ms</small></span>
              </div>
              <div class="stat-box full-width">
                <span class="lbl">最后一次扫描时间</span>
                <span class="val text-cyan">{{ fmtTime(runtimeObservation.last_due_poll_at) }}</span>
              </div>
            </div>
          </article>

          <article class="fui-panel flex-fill">
            <div class="panel-head">
              <span class="bracket">[</span> 系统关键事件 <span class="bracket">]</span>
            </div>
            <div v-if="recentEvents.length === 0" class="fui-empty">暂无关键事件记录</div>
            <div v-else class="timeline-wrap scroll-y">
              <div class="timeline-item" v-for="item in recentEvents" :key="item.id">
                <div class="tl-time">{{ fmtTime(item.created_at) }}</div>
                <div class="tl-content">
                  <div class="tl-type">{{ item.event_type }}</div>
                  <div class="tl-target fui-mono">关联ID: {{ item.target_id.substring(0,8) }}</div>
                  <div class="tl-msg" :title="eventMessage(item.details)">{{ eventMessage(item.details) }}</div>
                </div>
              </div>
            </div>
          </article>
        </div>

      </div>
    </div>
  </section>
</template>

<style scoped>
/* ================= 大屏整体框架 ================= */
.screen-wrapper {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 140px); /* 适应 App.vue 减去头部高度，充满屏幕 */
  min-height: 700px;
  animation: fadeIn 0.8s ease-out;
}

@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

/* ================= 头部设计 ================= */
.screen-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 20px;
  position: relative;
  padding-bottom: 15px;
}
.screen-header::after {
  content: ''; position: absolute; bottom: 0; left: 0; width: 100%; height: 2px;
  background: linear-gradient(90deg, transparent, #00f3ff 20%, #00f3ff 80%, transparent);
  box-shadow: 0 0 10px #00f3ff;
}

.header-title h2 { margin: 0; color: #fff; font-size: 26px; font-weight: 900; letter-spacing: 2px; text-shadow: 0 0 15px rgba(0, 243, 255, 0.8); }
.header-title span { color: #00f3ff; font-size: 14px; letter-spacing: 2px; opacity: 0.8; font-weight: bold; }

.fui-btn-glow {
  background: rgba(0, 243, 255, 0.1); border: 1px solid #00f3ff; color: #00f3ff;
  padding: 8px 24px; cursor: pointer; font-weight: bold;
  box-shadow: 0 0 10px rgba(0, 243, 255, 0.2) inset; transition: 0.3s;
  clip-path: polygon(10px 0, 100% 0, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0 100%, 0 10px);
}
.fui-btn-glow:hover { background: rgba(0, 243, 255, 0.3); box-shadow: 0 0 20px rgba(0, 243, 255, 0.6) inset; text-shadow: 0 0 5px #fff; }
.fui-btn-glow .icon { display: inline-block; margin-right: 5px; }

/* ================= 主体与 KPI ================= */
.screen-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
  overflow: hidden; /* 防止外层滚动，只在内部表格滚动 */
}

.kpi-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
}
.kpi-card {
  background: linear-gradient(180deg, rgba(0, 243, 255, 0.1) 0%, rgba(2, 18, 38, 0.8) 100%);
  border-top: 2px solid #00f3ff;
  padding: 15px 20px;
  position: relative;
}
.kpi-card::before { content: ''; position: absolute; top: 0; left: 0; width: 4px; height: 100%; background: #00f3ff; box-shadow: 0 0 10px #00f3ff; }
.kpi-label { color: #a0cfff; font-size: 13px; letter-spacing: 1px; margin-bottom: 5px; }
.kpi-value { font-size: 32px; font-weight: 900; font-family: 'DingTalk JinBuTi', Impact, sans-serif; }
.kpi-value .unit { font-size: 14px; margin-left: 5px; font-weight: normal; color: #a0cfff; }

/* ================= 三列布局 ================= */
.dashboard-grid {
  flex: 1;
  display: grid;
  grid-template-columns: 2.5fr 5fr 2.5fr; /* 经典的左右窄、中间宽的大屏比例 */
  gap: 20px;
  min-height: 0; /* 允许子元素截断高度并滚动 */
}

.ds-col { display: flex; flex-direction: column; gap: 20px; min-height: 0; }
.flex-fill { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.scroll-y { overflow-y: auto; overflow-x: hidden; }

/* 自定义滚动条 */
.scroll-y::-webkit-scrollbar { width: 4px; }
.scroll-y::-webkit-scrollbar-thumb { background: rgba(0, 243, 255, 0.5); border-radius: 2px; }
.scroll-y::-webkit-scrollbar-track { background: rgba(0,0,0,0.2); }

/* ================= 面板容器设计 ================= */
.fui-panel {
  background: rgba(2, 18, 38, 0.6);
  border: 1px solid rgba(0, 243, 255, 0.15);
  position: relative;
  padding: 16px;
  backdrop-filter: blur(5px);
}
/* 科技感四角括号框 */
.fui-panel::before, .fui-panel::after { content: ''; position: absolute; width: 20px; height: 20px; border: 2px solid transparent; pointer-events: none; }
.fui-panel::before { top: -1px; left: -1px; border-top-color: #00f3ff; border-left-color: #00f3ff; }
.fui-panel::after { bottom: -1px; right: -1px; border-bottom-color: #00f3ff; border-right-color: #00f3ff; }

/* 中心主面板特殊发光 */
.main-panel { background: rgba(2, 18, 38, 0.8); border: 1px solid rgba(0, 243, 255, 0.3); box-shadow: inset 0 0 30px rgba(0, 243, 255, 0.05); }

.panel-head {
  color: #fff; font-size: 16px; font-weight: bold; margin-bottom: 16px; display: flex; align-items: center; letter-spacing: 1px;
}
.panel-head .bracket { color: #00f3ff; margin: 0 6px; font-weight: normal; opacity: 0.7; }

.center-head { justify-content: center; font-size: 18px; color: #00f3ff; text-shadow: 0 0 10px rgba(0,243,255,0.5); position: relative; }
.center-head .head-glow { position: absolute; bottom: -5px; width: 60%; height: 2px; background: radial-gradient(circle, #00f3ff 0%, transparent 100%); }

/* ================= 左侧组件内容 ================= */
.tech-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 10px; }
.tech-list li { display: flex; justify-content: space-between; padding: 8px 12px; background: rgba(0, 243, 255, 0.03); border: 1px solid rgba(0, 243, 255, 0.1); }
.tech-list span { color: #a0cfff; font-size: 13px; }
.tech-list strong { color: #fff; font-size: 14px; }
.tech-list .col-span-full { flex-direction: column; gap: 4px; }

/* ================= 右侧组件内容 ================= */
.grid-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.stat-box { background: rgba(0,0,0,0.3); border: 1px solid rgba(0,243,255,0.1); padding: 10px; display: flex; flex-direction: column; }
.stat-box.full-width { grid-column: span 2; }
.stat-box .lbl { color: #8ab4f8; font-size: 12px; margin-bottom: 4px; }
.stat-box .val { color: #fff; font-size: 18px; font-weight: bold; font-family: 'Bebas Neue', 'JetBrains Mono', sans-serif; }

/* 时间轴样式 */
.timeline-wrap { padding-left: 10px; }
.timeline-item { position: relative; padding-left: 20px; padding-bottom: 15px; border-left: 1px solid rgba(0, 243, 255, 0.3); }
.timeline-item::before { content: ''; position: absolute; left: -5px; top: 2px; width: 9px; height: 9px; border-radius: 50%; background: #00f3ff; box-shadow: 0 0 5px #00f3ff; }
.tl-time { font-size: 12px; color: #a0cfff; margin-bottom: 4px; font-family: monospace; }
.tl-content { background: rgba(0, 243, 255, 0.05); padding: 8px; border-radius: 4px; }
.tl-type { color: #ffbb00; font-size: 13px; font-weight: bold; }
.tl-target { font-size: 11px; color: #8ab4f8; margin: 2px 0; }
.tl-msg { font-size: 12px; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* ================= 表格全局优化 ================= */
.fui-table-wrap { flex: 1; }
.fui-table { width: 100%; border-collapse: separate; border-spacing: 0 4px; }
.fui-table th { background: rgba(0, 243, 255, 0.08); color: #00f3ff; padding: 10px; text-align: left; font-size: 13px; border-bottom: 1px solid rgba(0,243,255,0.3); white-space: nowrap; }
.fui-table td { padding: 10px; color: #d0e8ff; font-size: 13px; background: rgba(0,0,0,0.2); }
.fui-table tr:hover td { background: rgba(0, 243, 255, 0.1); }
.density-high td, .density-high th { padding: 6px 10px; font-size: 12px; }

/* 中间主表格斑马线与高亮 */
.main-table tbody tr:nth-child(even) td { background: rgba(0, 243, 255, 0.02); }

/* ================= 通用原子类 ================= */
.fui-empty { padding: 30px; text-align: center; color: #6688aa; font-size: 14px; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; }
.data-safe { color: #00ffaa; font-weight: bold; text-shadow: 0 0 10px rgba(0, 255, 170, 0.3); }
.safe-icon { font-size: 24px; margin-bottom: 10px; }

.fui-mono, .font-num { font-family: "JetBrains Mono", Consolas, monospace; }
.text-cyan { color: #00f3ff !important; text-shadow: 0 0 5px rgba(0,243,255,0.5); }
.text-ok { color: #00ffaa !important; }
.text-warn { color: #ffbb00 !important; }
.text-err { color: #ff4444 !important; }

/* 状态徽章 */
.fui-badge { display: inline-flex; align-items: center; gap: 5px; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: bold; border: 1px solid transparent; }
.fui-badge .dot { width: 6px; height: 6px; border-radius: 50%; }
.fui-badge.completed { background: rgba(0, 255, 170, 0.1); border-color: #00ffaa; color: #00ffaa; }
.fui-badge.completed .dot { background: #00ffaa; box-shadow: 0 0 5px #00ffaa; }
.fui-badge.failed { background: rgba(255, 68, 68, 0.1); border-color: #ff4444; color: #ff4444; }
.fui-badge.failed .dot { background: #ff4444; box-shadow: 0 0 5px #ff4444; }
.fui-badge.running { background: rgba(0, 243, 255, 0.1); border-color: #00f3ff; color: #00f3ff; }
.fui-badge.running .dot { background: #00f3ff; box-shadow: 0 0 5px #00f3ff; animation: blink 1s infinite alternate; }

/* 呼吸灯动效 */
.text-pulse { animation: blink 1.5s infinite alternate; text-shadow: 0 0 10px #00ffaa; }
@keyframes blink { 0% { opacity: 0.5; } 100% { opacity: 1; } }
</style>