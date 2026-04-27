<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  getRunDiagnostics,
  listModelBindingHealth,
  type ModelBindingHealthPayload,
  type ModelBindingHealthRecord,
  type RunDiagnosticsPayload,
} from '../api/runtimeDiagnostics'

const loading = ref(false)
const error = ref('')
const bindingPayload = ref<ModelBindingHealthPayload | null>(null)
const selectedInstanceId = ref<number | null>(null)
const runId = ref('')
const runDiagnostics = ref<RunDiagnosticsPayload | null>(null)
const runLoading = ref(false)
const runError = ref('')

const healthItems = computed(() => bindingPayload.value?.items ?? [])
const selectedHealth = computed(() => {
  if (selectedInstanceId.value == null) return null
  return healthItems.value.find((item) => item.instance_id === selectedInstanceId.value) ?? null
})

const summaryCards = computed(() => {
  const severity = bindingPayload.value?.severity_summary ?? {}
  const status = bindingPayload.value?.summary ?? {}
  return [
    { label: '实例总数', value: String(bindingPayload.value?.total ?? 0), tone: 'info' },
    { label: '正常绑定', value: String(severity.ok ?? 0), tone: 'ok' },
    { label: '警告', value: String(severity.warning ?? 0), tone: 'warning' },
    { label: '错误', value: String(severity.error ?? 0), tone: 'error' },
    { label: '未声明模型依赖', value: String(status.NO_MODEL_REQUIREMENT ?? 0), tone: 'info' },
  ]
})

function statusClass(item: Pick<ModelBindingHealthRecord, 'severity' | 'status'> | null) {
  if (!item) return 'badge-info'
  if (item.severity === 'ok') return 'badge-ok'
  if (item.severity === 'warning') return 'badge-warning'
  if (item.severity === 'error') return 'badge-error'
  return 'badge-info'
}

function stringify(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2)
}

function modelName(item: ModelBindingHealthRecord) {
  const model = item.model as Record<string, unknown> | null
  return typeof model?.model_name === 'string' ? model.model_name : '-'
}

function versionName(item: ModelBindingHealthRecord) {
  const version = item.version as Record<string, unknown> | null
  return typeof version?.version === 'string' ? version.version : '-'
}

function selectHealth(item: ModelBindingHealthRecord) {
  selectedInstanceId.value = item.instance_id
}

async function loadHealth() {
  loading.value = true
  error.value = ''
  try {
    bindingPayload.value = await listModelBindingHealth()
    if (selectedInstanceId.value == null && healthItems.value.length > 0) {
      selectedInstanceId.value = healthItems.value[0].instance_id
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '模型绑定健康状态加载失败'
  } finally {
    loading.value = false
  }
}

async function loadRunDiagnostics() {
  const value = runId.value.trim()
  if (!value) return
  runLoading.value = true
  runError.value = ''
  runDiagnostics.value = null
  try {
    runDiagnostics.value = await getRunDiagnostics(value)
  } catch (err) {
    runError.value = err instanceof Error ? err.message : '运行诊断加载失败'
  } finally {
    runLoading.value = false
  }
}

onMounted(loadHealth)
</script>

<template>
  <div class="diag-page">
    <section class="diag-hero panel">
      <div>
        <p class="eyebrow">RUNTIME DIAGNOSTICS</p>
        <h2>运行诊断与模型绑定健康检查</h2>
        <p class="desc">聚合实例模型绑定、family_fingerprint、requiredArtifacts、运行 metrics、回写状态和故障建议。</p>
      </div>
      <button class="cyber-btn" type="button" @click="loadHealth" :disabled="loading">
        {{ loading ? '刷新中...' : '刷新健康状态' }}
      </button>
    </section>

    <p v-if="error" class="error-line">{{ error }}</p>

    <section class="summary-grid">
      <article v-for="card in summaryCards" :key="card.label" class="metric-card" :class="`tone-${card.tone}`">
        <span>{{ card.label }}</span>
        <strong>{{ card.value }}</strong>
      </article>
    </section>

    <section class="layout-grid">
      <article class="panel list-panel">
        <div class="panel-title-row">
          <h3>实例绑定健康</h3>
          <span class="count">{{ healthItems.length }} ITEMS</span>
        </div>
        <div v-if="!loading && healthItems.length === 0" class="empty">暂无实例</div>
        <button
          v-for="item in healthItems"
          :key="item.instance_id"
          type="button"
          class="health-row"
          :class="{ active: item.instance_id === selectedInstanceId }"
          @click="selectHealth(item)"
        >
          <div class="row-main">
            <strong>{{ item.instance_name || `Instance #${item.instance_id}` }}</strong>
            <span>{{ item.package_name }}@{{ item.plugin_version }}</span>
          </div>
          <span :class="['badge', statusClass(item)]">{{ item.status }}</span>
        </button>
      </article>

      <article class="panel detail-panel">
        <div class="panel-title-row">
          <h3>绑定详情</h3>
          <span v-if="selectedHealth" :class="['badge', statusClass(selectedHealth)]">{{ selectedHealth.severity }}</span>
        </div>
        <div v-if="!selectedHealth" class="empty">请选择实例</div>
        <template v-else>
          <div class="kv-grid">
            <div><label>实例 ID</label><strong>{{ selectedHealth.instance_id }}</strong></div>
            <div><label>插件</label><strong>{{ selectedHealth.package_name }}@{{ selectedHealth.plugin_version }}</strong></div>
            <div><label>插件指纹</label><strong class="mono">{{ selectedHealth.plugin_family_fingerprint || '-' }}</strong></div>
            <div><label>模型</label><strong>{{ modelName(selectedHealth) }}</strong></div>
            <div><label>模型版本</label><strong>{{ versionName(selectedHealth) }}</strong></div>
            <div><label>状态</label><strong>{{ selectedHealth.status }}</strong></div>
          </div>
          <p class="message">{{ selectedHealth.message }}</p>

          <h4>Artifacts 检查</h4>
          <div class="artifact-grid">
            <div>
              <label>requiredArtifacts</label>
              <pre>{{ stringify(selectedHealth.artifact_check.required_artifacts) }}</pre>
            </div>
            <div>
              <label>模型 artifacts</label>
              <pre>{{ stringify(selectedHealth.artifact_check.artifact_keys) }}</pre>
            </div>
            <div>
              <label>缺失 key</label>
              <pre>{{ stringify(selectedHealth.artifact_check.missing_required_keys) }}</pre>
            </div>
            <div>
              <label>缺失文件</label>
              <pre>{{ stringify(selectedHealth.artifact_check.missing_files) }}</pre>
            </div>
          </div>
        </template>
      </article>
    </section>

    <section class="panel run-panel">
      <div class="panel-title-row">
        <h3>单次运行诊断</h3>
        <span class="count">RUN ID</span>
      </div>
      <form class="run-form" @submit.prevent="loadRunDiagnostics">
        <input v-model="runId" class="cyber-input" placeholder="run-xxxxxxxx" />
        <button class="cyber-btn" type="submit" :disabled="runLoading || !runId.trim()">
          {{ runLoading ? '诊断中...' : '诊断运行' }}
        </button>
      </form>
      <p v-if="runError" class="error-line">{{ runError }}</p>

      <div v-if="runDiagnostics" class="run-detail-grid">
        <article class="sub-panel">
          <h4>模型运行指标</h4>
          <pre>{{ stringify(runDiagnostics.model_metrics) }}</pre>
        </article>
        <article class="sub-panel">
          <h4>回写摘要</h4>
          <pre>{{ stringify(runDiagnostics.writeback_summary) }}</pre>
        </article>
        <article class="sub-panel wide">
          <h4>诊断建议</h4>
          <div v-if="runDiagnostics.suggestions.length === 0" class="empty">未发现明显异常</div>
          <div v-for="item in runDiagnostics.suggestions" :key="`${item.code}-${item.message}`" class="suggestion" :class="`suggestion-${item.level}`">
            <strong>{{ item.code }}</strong>
            <span>{{ item.message }}</span>
          </div>
        </article>
        <article class="sub-panel wide">
          <h4>绑定健康快照</h4>
          <pre>{{ stringify(runDiagnostics.model_binding_health) }}</pre>
        </article>
      </div>
    </section>
  </div>
</template>

<style scoped>
.diag-page {
  min-height: 100vh;
  color: #d8f7ff;
  font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
}
.panel,
.metric-card,
.sub-panel {
  background: rgba(3, 17, 31, 0.86);
  border: 1px solid rgba(0, 243, 255, 0.24);
  box-shadow: 0 0 28px rgba(0, 0, 0, 0.3), inset 0 0 18px rgba(0, 243, 255, 0.04);
}
.diag-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 28px;
  margin-bottom: 20px;
}
.eyebrow {
  margin: 0 0 8px;
  color: #00f3ff;
  letter-spacing: 0.22em;
  font-size: 12px;
}
h2, h3, h4 { margin: 0; }
.desc { margin: 10px 0 0; color: rgba(216, 247, 255, 0.62); }
.cyber-btn {
  background: rgba(0, 243, 255, 0.12);
  border: 1px solid #00f3ff;
  color: #00f3ff;
  padding: 10px 18px;
  font-weight: 700;
  cursor: pointer;
  clip-path: polygon(8px 0,100% 0,100% calc(100% - 8px),calc(100% - 8px) 100%,0 100%,0 8px);
}
.cyber-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.error-line {
  padding: 12px 16px;
  color: #ff6688;
  border: 1px solid rgba(255, 80, 120, 0.36);
  background: rgba(255, 80, 120, 0.08);
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(120px, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}
.metric-card { padding: 18px; }
.metric-card span { display: block; color: rgba(216, 247, 255, 0.55); font-size: 12px; }
.metric-card strong { display: block; margin-top: 8px; font-size: 28px; color: #fff; }
.tone-ok strong { color: #00ffcc; }
.tone-warning strong { color: #ffaa00; }
.tone-error strong { color: #ff6688; }
.tone-info strong { color: #00f3ff; }
.layout-grid {
  display: grid;
  grid-template-columns: minmax(360px, 0.9fr) minmax(520px, 1.4fr);
  gap: 20px;
}
.list-panel,
.detail-panel,
.run-panel { padding: 22px; }
.panel-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}
.count { color: rgba(0, 243, 255, 0.65); font-size: 12px; }
.health-row {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 10px;
  padding: 14px;
  text-align: left;
  color: inherit;
  background: rgba(0, 20, 38, 0.78);
  border: 1px solid rgba(0, 243, 255, 0.16);
  cursor: pointer;
}
.health-row.active,
.health-row:hover { border-color: rgba(0, 243, 255, 0.72); background: rgba(0, 243, 255, 0.08); }
.row-main strong { display: block; color: #fff; }
.row-main span { display: block; margin-top: 4px; color: rgba(216, 247, 255, 0.54); font-size: 12px; }
.badge {
  display: inline-flex;
  align-items: center;
  white-space: nowrap;
  padding: 4px 8px;
  border: 1px solid currentColor;
  font-size: 11px;
  font-weight: 800;
}
.badge-ok { color: #00ffcc; background: rgba(0, 255, 204, 0.08); }
.badge-warning { color: #ffaa00; background: rgba(255, 170, 0, 0.08); }
.badge-error { color: #ff6688; background: rgba(255, 102, 136, 0.08); }
.badge-info { color: #00f3ff; background: rgba(0, 243, 255, 0.08); }
.kv-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.kv-grid div,
.artifact-grid div {
  padding: 12px;
  background: rgba(0, 10, 20, 0.58);
  border: 1px solid rgba(0, 243, 255, 0.14);
}
label { display: block; margin-bottom: 6px; color: rgba(216, 247, 255, 0.48); font-size: 12px; }
.mono { font-family: Consolas, monospace; }
.message { padding: 12px; color: #00f3ff; background: rgba(0, 243, 255, 0.06); border-left: 3px solid #00f3ff; }
.artifact-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(240px, 1fr));
  gap: 12px;
}
pre {
  margin: 0;
  color: #b8f7ff;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: Consolas, monospace;
  font-size: 12px;
}
.empty { color: rgba(216, 247, 255, 0.5); padding: 18px; }
.run-panel { margin-top: 20px; }
.run-form { display: flex; gap: 12px; margin-bottom: 18px; }
.cyber-input {
  flex: 1;
  background: rgba(0, 8, 16, 0.92);
  border: 1px solid rgba(0, 243, 255, 0.3);
  color: #d8f7ff;
  padding: 10px 12px;
  outline: none;
}
.run-detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(260px, 1fr));
  gap: 14px;
}
.sub-panel { padding: 16px; }
.sub-panel h4 { margin-bottom: 12px; color: #00f3ff; }
.sub-panel.wide { grid-column: 1 / -1; }
.suggestion {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
  padding: 12px;
  border: 1px solid rgba(0, 243, 255, 0.18);
  background: rgba(0, 10, 20, 0.58);
}
.suggestion-error { border-color: rgba(255, 102, 136, 0.42); }
.suggestion-warning { border-color: rgba(255, 170, 0, 0.42); }
.suggestion-info { border-color: rgba(0, 243, 255, 0.32); }
.suggestion strong { color: #fff; }
.suggestion span { color: rgba(216, 247, 255, 0.72); }
@media (max-width: 1100px) {
  .summary-grid { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
  .layout-grid { grid-template-columns: 1fr; }
  .diag-hero { flex-direction: column; align-items: flex-start; }
}
</style>
