<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  listModelBindingHealth,
  type ModelBindingHealthPayload,
  type ModelBindingHealthRecord,
} from '../api/runtimeDiagnostics'

const loading = ref(false)
const error = ref('')
const bindingPayload = ref<ModelBindingHealthPayload | null>(null)
const selectedInstanceId = ref<number | null>(null)

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
  </div>
</template>

<style scoped>
/* 整体页面容器 */
.diag-hero.panel {
  width: 100% !important;
  max-width: 100% !important;
  box-sizing: border-box !important;
  margin-left: 0 !important;
  margin-right: 0 !important;
}

/* 面板通用样式 */
.panel {
  background: rgba(3, 17, 31, 0.86);
  border: 1px solid rgba(0, 243, 255, 0.24);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25), inset 0 0 18px rgba(0, 243, 255, 0.04);
  border-radius: 6px;
  box-sizing: border-box !important;
}
.metric-card {
  background: rgba(3, 17, 31, 0.86);
  border: 1px solid rgba(0, 243, 255, 0.24);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25), inset 0 0 18px rgba(0, 243, 255, 0.04);
  border-radius: 6px;
}

/* 顶部标题区 */
.diag-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 16px 20px;
  margin-bottom: 16px;
}

.eyebrow {
  margin: 0 0 4px;
  color: #00f3ff;
  letter-spacing: 0.2em;
  font-size: 11px;
}

h2 { margin: 0; font-size: 20px; color: #fff; }
h3 { margin: 0; font-size: 16px; color: #fff; }
h4 { margin: 0 0 10px 0; font-size: 14px; color: #00f3ff; }

.desc { margin: 6px 0 0; color: rgba(216, 247, 255, 0.62); font-size: 12px; }

/* 按钮 */
.cyber-btn {
  background: rgba(0, 243, 255, 0.08);
  border: 1px solid #00f3ff;
  color: #00f3ff;
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s ease;
  white-space: nowrap;
}
.cyber-btn:hover:not(:disabled) {
  background: #00f3ff;
  color: #04121f;
  box-shadow: 0 0 12px rgba(0, 243, 255, 0.4);
}
.cyber-btn:disabled { opacity: 0.3; cursor: not-allowed; filter: grayscale(1); }

/* 错误提示 */
.error-line {
  padding: 10px 14px;
  margin-bottom: 16px;
  color: #ff6688;
  font-size: 12px;
  border: 1px solid rgba(255, 80, 120, 0.36);
  background: rgba(255, 80, 120, 0.08);
  border-radius: 4px;
}

/* 汇总卡片 */
.summary-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(120px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.metric-card { padding: 14px 16px; }
.metric-card span { display: block; color: rgba(216, 247, 255, 0.55); font-size: 11px; }
.metric-card strong { display: block; margin-top: 6px; font-size: 22px; color: #fff; }
.tone-ok strong { color: #00ffcc; }
.tone-warning strong { color: #ffaa00; }
.tone-error strong { color: #ff6688; }
.tone-info strong { color: #00f3ff; }

/* 左右分栏布局 */
.layout-grid {
  display: grid !important;
  grid-template-columns: 320px minmax(0, 1fr) !important;
  gap: 20px !important;
  align-items: start !important;
  width: 100% !important;
  margin: 0 !important;
}

.list-panel {
  padding: 16px !important;
  width: 100% !important;
  max-width: none !important;
  margin: 0 !important;
}
.detail-panel {
  padding: 16px !important;
  width: 100% !important;
  max-width: none !important;
  margin: 0 !important;
}

.panel-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px dashed rgba(0, 243, 255, 0.15);
}
.count { color: rgba(0, 243, 255, 0.65); font-size: 11px; background: rgba(0, 243, 255, 0.1); padding: 2px 6px; border-radius: 10px;}

/* 左侧列表项 */
.health-row {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
  padding: 10px 12px;
  text-align: left;
  color: inherit;
  background: rgba(0, 20, 38, 0.4);
  border: 1px solid rgba(0, 243, 255, 0.1);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
}
.health-row:hover {
  border-color: rgba(0, 243, 255, 0.5);
  background: rgba(0, 243, 255, 0.05);
}
.health-row.active {
  border-color: #00f3ff; 
  background: rgba(0, 243, 255, 0.12); 
  box-shadow: inset 3px 0 0 #00f3ff;
}
.row-main strong { display: block; color: #fff; font-size: 13px; margin-bottom: 2px;}
.row-main span { display: block; color: rgba(216, 247, 255, 0.54); font-size: 11px; }

/* 状态徽章 */
.badge {
  display: inline-flex;
  align-items: center;
  white-space: nowrap;
  padding: 2px 6px;
  border: 1px solid currentColor;
  border-radius: 2px;
  font-size: 11px;
}
.badge-ok { color: #00ffcc; background: rgba(0, 255, 204, 0.08); }
.badge-warning { color: #ffaa00; background: rgba(255, 170, 0, 0.08); }
.badge-error { color: #ff6688; background: rgba(255, 102, 136, 0.08); }
.badge-info { color: #00f3ff; background: rgba(0, 243, 255, 0.08); }

/* 详情网格 */
.kv-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(180px, 1fr));
  gap: 8px;
  margin-bottom: 14px;
}
.kv-grid div,
.artifact-grid div {
  padding: 10px 12px;
  background: rgba(0, 10, 20, 0.58);
  border: 1px solid rgba(0, 243, 255, 0.12);
  border-radius: 4px;
}
label { display: block; margin-bottom: 4px; color: rgba(216, 247, 255, 0.5); font-size: 11px; }
.kv-grid strong { font-size: 13px; word-break: break-all; }
.mono { font-family: Consolas, monospace; font-size: 12px; opacity: 0.8;}

.message { 
  padding: 10px 12px; 
  margin-bottom: 16px;
  font-size: 12px;
  color: #00f3ff; 
  background: rgba(0, 243, 255, 0.06); 
  border-left: 3px solid #00f3ff; 
  border-radius: 0 4px 4px 0;
}

.artifact-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(200px, 1fr));
  gap: 10px;
}

/* 代码块 */
pre {
  margin: 0;
  color: #b8f7ff;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: Consolas, monospace;
  font-size: 12px;
  max-height: 180px;
  overflow-y: auto;
  background: rgba(0, 0, 0, 0.2);
  padding: 8px;
  border-radius: 2px;
}
pre::-webkit-scrollbar { width: 4px; }
pre::-webkit-scrollbar-thumb { background: rgba(0, 243, 255, 0.3); border-radius: 2px;}
pre::-webkit-scrollbar-track { background: transparent; }

.empty { color: rgba(216, 247, 255, 0.4); padding: 20px; text-align: center; font-size: 12px;}

/* 响应式 */
@media (max-width: 1100px) {
  .summary-grid { grid-template-columns: repeat(3, minmax(120px, 1fr)); }
  .diag-hero { flex-direction: column; align-items: flex-start; gap: 12px;}
  .layout-grid { 
    grid-template-columns: 1fr !important; 
  }
}
</style>