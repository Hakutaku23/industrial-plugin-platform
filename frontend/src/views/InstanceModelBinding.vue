<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  deleteInstanceModelBinding,
  bindInstanceModel,
  getInstanceModelBinding,
  getInstanceModelBindingHealth,
  getInstanceModelRequirement,
  listModels,
  listModelVersions,
  type InstanceModelRequirement,
  type ModelBindingHealthRecord,
  type ModelBindingRecord,
  type ModelHealthIssue,
  type ModelSummary,
  type ModelVersionRecord,
} from '../api/models'
import {
  listInstances,
  type PluginInstanceRecord,
} from '../api/packages'

const instances = ref<PluginInstanceRecord[]>([])
const models = ref<ModelSummary[]>([])
const versions = ref<ModelVersionRecord[]>([])
const selectedInstanceId = ref<number | null>(null)
const selectedModelId = ref<number | null>(null)
const selectedVersionId = ref<number | null>(null)
const bindingMode = ref<'current' | 'fixed_version'>('current')
const currentBinding = ref<ModelBindingRecord | null>(null)
const requirement = ref<InstanceModelRequirement | null>(null)
const health = ref<ModelBindingHealthRecord | null>(null)
const loading = ref(false)
const healthLoading = ref(false)
const saving = ref(false)
const error = ref('')
const message = ref('')

const selectedInstance = computed(() => instances.value.find((item) => item.id === selectedInstanceId.value) ?? null)
const requiredFingerprint = computed(() => requirement.value?.family_fingerprint || '')
const compatibleModels = computed(() => {
  const fingerprint = requiredFingerprint.value
  if (!fingerprint) return []
  return models.value.filter((model) => model.family_fingerprint === fingerprint)
})
const selectedModel = computed(() => models.value.find((item) => item.id === selectedModelId.value) ?? null)
const activeVersionLabel = computed(() => selectedModel.value?.active_version || '未上线')
const selectedModelCompatible = computed(() => {
  if (!selectedModel.value || !requiredFingerprint.value) return false
  return selectedModel.value.family_fingerprint === requiredFingerprint.value
})
const canBind = computed(() => {
  if (!selectedInstanceId.value || !selectedModelId.value) return false
  if (!requiredFingerprint.value) return false
  if (!selectedModelCompatible.value) return false
  if (bindingMode.value === 'fixed_version' && !selectedVersionId.value) return false
  return true
})
const healthStatusClass = computed(() => {
  const status = String(health.value?.status || '').toUpperCase()
  if (!health.value) return 'health-muted'
  if (health.value.healthy) return 'health-ok'
  if (status === 'NO_MODEL_REQUIREMENT') return 'health-muted'
  return 'health-error'
})
const healthTitle = computed(() => {
  if (!health.value) return '未读取健康状态'
  if (health.value.healthy) return '模型绑定健康'
  if (health.value.status === 'NO_MODEL_REQUIREMENT') return '该插件未声明模型依赖'
  return '模型绑定存在阻断项'
})

async function loadAll() {
  loading.value = true
  error.value = ''
  message.value = ''
  try {
    instances.value = await listInstances()
    models.value = await listModels()
    if (!selectedInstanceId.value && instances.value.length > 0) {
      selectedInstanceId.value = instances.value[0].id
    }
    await loadSelectedInstanceState()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '实例模型绑定数据加载失败'
  } finally {
    loading.value = false
  }
}

async function loadSelectedInstanceState() {
  await loadRequirement()
  applyDefaultCompatibleModel()
  await loadVersions()
  await loadCurrentBinding()
  await loadHealth()
}

async function loadRequirement() {
  requirement.value = null
  if (!selectedInstanceId.value) return
  try {
    requirement.value = await getInstanceModelRequirement(selectedInstanceId.value)
  } catch (err) {
    requirement.value = null
    error.value = err instanceof Error ? err.message : '读取插件模型指纹要求失败'
  }
}

async function loadHealth() {
  health.value = null
  if (!selectedInstanceId.value) return
  healthLoading.value = true
  try {
    health.value = await getInstanceModelBindingHealth(selectedInstanceId.value)
  } catch (err) {
    health.value = {
      instance_id: selectedInstanceId.value,
      healthy: false,
      status: 'HEALTH_ENDPOINT_FAILED',
      errors: [{ code: 'E_HEALTH_ENDPOINT_FAILED', message: err instanceof Error ? err.message : '健康检查接口调用失败' }],
      warnings: [],
      requirement: null,
      binding: null,
      model: null,
      version: null,
      checked_at: null,
    }
  } finally {
    healthLoading.value = false
  }
}

function applyDefaultCompatibleModel() {
  const currentStillCompatible = compatibleModels.value.some((item) => item.id === selectedModelId.value)
  if (!currentStillCompatible) {
    selectedModelId.value = compatibleModels.value[0]?.id ?? null
  }
}

async function loadVersions() {
  versions.value = selectedModelId.value ? await listModelVersions(selectedModelId.value) : []
  if (bindingMode.value === 'fixed_version' && !versions.value.some((item) => item.id === selectedVersionId.value)) {
    selectedVersionId.value = versions.value[0]?.id ?? null
  }
}

async function loadCurrentBinding() {
  currentBinding.value = null
  if (!selectedInstanceId.value) return
  try {
    currentBinding.value = await getInstanceModelBinding(selectedInstanceId.value)
    selectedModelId.value = currentBinding.value.model_id
    bindingMode.value = currentBinding.value.binding_mode
    selectedVersionId.value = currentBinding.value.model_version_id
    await loadVersions()
  } catch {
    currentBinding.value = null
  }
}

async function submitBinding() {
  if (!canBind.value || !selectedInstanceId.value || !selectedModelId.value) return
  saving.value = true
  error.value = ''
  message.value = ''
  try {
    currentBinding.value = await bindInstanceModel({
      instanceId: selectedInstanceId.value,
      model_id: selectedModelId.value,
      binding_mode: bindingMode.value,
      model_version_id: bindingMode.value === 'fixed_version' ? selectedVersionId.value : null,
    })
    message.value = '模型绑定已保存，family_fingerprint 已通过后端强校验'
    await loadHealth()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '模型绑定保存失败'
    await loadHealth()
  } finally {
    saving.value = false
  }
}

async function clearBinding() {
  if (!selectedInstanceId.value) return
  saving.value = true
  error.value = ''
  message.value = ''
  try {
    await deleteInstanceModelBinding(selectedInstanceId.value)
    currentBinding.value = null
    message.value = '模型绑定已解除'
    await loadHealth()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '解除绑定失败'
  } finally {
    saving.value = false
  }
}

function statusClass(status: string) {
  const normalized = status.toLowerCase()
  if (normalized.includes('active')) return 'status-online'
  if (normalized.includes('validated')) return 'status-ok'
  if (normalized.includes('uploaded')) return 'status-warn'
  if (normalized.includes('running')) return 'status-online'
  if (normalized.includes('failed')) return 'status-error'
  return 'status-muted'
}

function issueClass(issue: ModelHealthIssue) {
  if (issue.code.includes('WARNING') || issue.code.includes('WARN')) return 'issue-warn'
  return 'issue-error'
}

function stringify(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2)
}

watch(selectedModelId, async () => {
  await loadVersions()
})

watch(selectedInstanceId, async () => {
  error.value = ''
  message.value = ''
  await loadSelectedInstanceState()
})

onMounted(loadAll)
</script>

<template>
  <div class="cyber-container">
    <section class="panel">
      <div class="corner-tl"></div><div class="corner-tr"></div>
      <div class="corner-bl"></div><div class="corner-br"></div>

      <div class="intro">
        <div>
          <p class="eyebrow">INSTANCE MODEL BINDING</p>
          <h2 class="page-title">实例模型绑定</h2>
          <p class="page-desc">只允许绑定 family_fingerprint 与插件声明一致的模型；健康检查会同步检查 active 版本、固定版本、artifact 文件与 checksum。</p>
        </div>
        <div class="intro-actions">
          <button type="button" class="cyber-button-outline" :disabled="loading" @click="loadAll">刷新</button>
          <button type="button" class="cyber-button-outline" :disabled="healthLoading || !selectedInstanceId" @click="loadHealth">健康检查</button>
        </div>
      </div>

      <div v-if="error" class="error-banner"><span class="blink">!</span> ERROR: {{ error }}</div>
      <div v-if="message" class="success-banner">{{ message }}</div>

      <div class="layout-grid">
        <aside class="instance-list">
          <div class="section-tag">实例列表</div>
          <button
            v-for="item in instances"
            :key="item.id"
            type="button"
            class="instance-card"
            :class="{ active: selectedInstanceId === item.id }"
            @click="selectedInstanceId = item.id"
          >
            <span class="name">{{ item.name }}</span>
            <span class="meta">{{ item.package_name }}@{{ item.version }}</span>
            <span class="status" :class="statusClass(item.status)">{{ item.status }}</span>
          </button>
          <div v-if="!instances.length && !loading" class="empty">暂无实例</div>
        </aside>

        <main class="binding-panel">
          <div class="section-tag">绑定配置</div>

          <div v-if="selectedInstance" class="selected-box">
            <label>当前实例</label>
            <strong>{{ selectedInstance.name }}</strong>
            <span>{{ selectedInstance.package_name }}@{{ selectedInstance.version }}</span>
          </div>

          <div class="health-card" :class="healthStatusClass">
            <div class="health-head">
              <div>
                <label>绑定健康状态</label>
                <strong>{{ healthTitle }}</strong>
              </div>
              <span class="health-badge">{{ healthLoading ? 'CHECKING' : (health?.status || 'UNKNOWN') }}</span>
            </div>
            <div v-if="health?.errors?.length" class="issue-list">
              <div v-for="item in health.errors" :key="`${item.code}:${item.message}`" class="issue-item" :class="issueClass(item)">
                <code>{{ item.code }}</code>
                <span>{{ item.message }}</span>
              </div>
            </div>
            <div v-if="health?.warnings?.length" class="issue-list">
              <div v-for="item in health.warnings" :key="`${item.code}:${item.message}`" class="issue-item issue-warn">
                <code>{{ item.code }}</code>
                <span>{{ item.message }}</span>
              </div>
            </div>
            <p v-if="health?.healthy" class="health-ok-text">运行前模型绑定校验通过。</p>
          </div>

          <div class="requirement-box" :class="{ blocked: !requiredFingerprint }">
            <label>插件声明的模型指纹</label>
            <code v-if="requiredFingerprint">{{ requiredFingerprint }}</code>
            <strong v-else>未声明 modelDependency.familyFingerprint，禁止绑定模型</strong>
            <span>{{ requirement?.message || '尚未读取插件模型依赖声明' }}</span>
          </div>

          <div class="form-grid">
            <label class="field">
              <span>兼容模型</span>
              <select v-model.number="selectedModelId" :disabled="!requiredFingerprint">
                <option :value="null">请选择模型</option>
                <option v-for="model in compatibleModels" :key="model.id" :value="model.id">
                  {{ model.display_name || model.model_name }} / active: {{ model.active_version || '未上线' }}
                </option>
              </select>
            </label>

            <label class="field">
              <span>绑定模式</span>
              <select v-model="bindingMode" :disabled="!requiredFingerprint">
                <option value="current">跟随当前 active 版本</option>
                <option value="fixed_version">固定指定模型版本</option>
              </select>
            </label>

            <label v-if="bindingMode === 'fixed_version'" class="field full">
              <span>固定版本</span>
              <select v-model.number="selectedVersionId">
                <option :value="null">请选择模型版本</option>
                <option v-for="version in versions" :key="version.id" :value="version.id">
                  {{ version.version }} / {{ version.status }} / {{ version.created_at }}
                </option>
              </select>
            </label>
          </div>

          <div v-if="requiredFingerprint && compatibleModels.length === 0" class="warning-panel">
            没有发现与该插件 family_fingerprint 匹配的模型。请上传模型包，并确保模型包中的 model_family.family_fingerprint 与插件声明一致。
          </div>

          <div v-if="selectedModel" class="model-summary">
            <div>
              <label>模型名称</label>
              <strong>{{ selectedModel.model_name }}</strong>
            </div>
            <div>
              <label>active 版本</label>
              <strong>{{ activeVersionLabel }}</strong>
            </div>
            <div>
              <label>模型状态</label>
              <strong :class="statusClass(selectedModel.status)">{{ selectedModel.status }}</strong>
            </div>
            <div class="full">
              <label>family_fingerprint</label>
              <code>{{ selectedModel.family_fingerprint }}</code>
            </div>
          </div>

          <div v-if="currentBinding" class="current-binding">
            <div class="section-tag">当前绑定</div>
            <div class="binding-grid">
              <div>
                <label>模型</label>
                <span>{{ currentBinding.model_name }}</span>
              </div>
              <div>
                <label>模式</label>
                <span>{{ currentBinding.binding_mode }}</span>
              </div>
              <div>
                <label>固定版本 ID</label>
                <span>{{ currentBinding.model_version_id ?? '-' }}</span>
              </div>
              <div>
                <label>指纹校验</label>
                <span :class="currentBinding.fingerprint_match ? 'status-online' : 'status-warn'">
                  {{ currentBinding.fingerprint_match ? 'MATCH' : 'UNKNOWN / MISMATCH' }}
                </span>
              </div>
              <div class="full">
                <label>模型指纹</label>
                <code>{{ currentBinding.family_fingerprint }}</code>
              </div>
            </div>
          </div>

          <details v-if="health" class="raw-details">
            <summary>查看健康检查原始数据</summary>
            <pre>{{ stringify(health) }}</pre>
          </details>

          <div class="action-row">
            <button type="button" class="cyber-submit-btn" :disabled="saving || !canBind" @click="submitBinding">
              {{ saving ? '保存中...' : '保存绑定' }}
            </button>
            <button type="button" class="danger-btn" :disabled="saving || !currentBinding" @click="clearBinding">
              解除绑定
            </button>
          </div>
        </main>
      </div>

      <div class="hint-panel">
        <div class="section-tag">插件声明示例</div>
        <pre>modelDependency:
  required: true
  familyFingerprint: mf_redis_sine_sklearn_regressor_v1
  requiredArtifacts:
    - model
    - x_scaler</pre>
      </div>
    </section>
  </div>
</template>

<style scoped>
.cyber-container {
  --cyan: #00f2ff;
  --bg-deep: #010a12;
  --panel-bg: rgba(2, 15, 26, 0.72);
  --border-cyan: rgba(0, 242, 255, 0.32);
  --border-cyan-strong: rgba(0, 242, 255, 0.72);
  --text-white: rgba(255, 255, 255, 0.95);
  --text-dim: rgba(255, 255, 255, 0.55);
  min-height: 100vh;
  padding: 40px 20px;
  color: var(--text-white);
  background:
    linear-gradient(rgba(0, 242, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 242, 255, 0.03) 1px, transparent 1px),
    var(--bg-deep);
  background-size: 30px 30px;
}

.panel {
  max-width: 1280px;
  margin: 0 auto;
  position: relative;
  background: var(--panel-bg);
  border: 1px solid var(--border-cyan);
  padding: 34px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
}

[class^="corner-"] { position: absolute; width: 15px; height: 15px; border: 2px solid var(--cyan); }
.corner-tl { top: -2px; left: -2px; border-right: 0; border-bottom: 0; }
.corner-tr { top: -2px; right: -2px; border-left: 0; border-bottom: 0; }
.corner-bl { bottom: -2px; left: -2px; border-right: 0; border-top: 0; }
.corner-br { bottom: -2px; right: -2px; border-left: 0; border-top: 0; }

.intro { display: flex; justify-content: space-between; align-items: center; gap: 24px; margin-bottom: 28px; }
.intro-actions { display: flex; gap: 12px; flex-wrap: wrap; }
.eyebrow, .section-tag { font-size: 11px; letter-spacing: 3px; color: var(--cyan); margin: 0 0 10px; }
.page-title { margin: 0 0 8px; font-size: 28px; color: #fff; }
.page-desc { margin: 0; color: var(--text-dim); font-size: 13px; }

.layout-grid { display: grid; grid-template-columns: 360px 1fr; gap: 24px; }
.instance-list, .binding-panel, .hint-panel {
  background: rgba(1, 10, 18, 0.7);
  border: 1px solid var(--border-cyan);
  padding: 20px;
}

.instance-card {
  width: 100%;
  display: grid;
  gap: 6px;
  margin-bottom: 10px;
  padding: 14px;
  text-align: left;
  color: var(--text-white);
  border: 1px solid rgba(0, 242, 255, 0.18);
  background: rgba(0, 242, 255, 0.04);
  cursor: pointer;
}
.instance-card.active {
  border-color: var(--border-cyan-strong);
  background: rgba(0, 242, 255, 0.12);
  box-shadow: inset 0 0 18px rgba(0, 242, 255, 0.12);
}
.instance-card .name { font-weight: 800; }
.instance-card .meta { color: var(--text-dim); font-size: 12px; }
.status { width: fit-content; font-size: 11px; padding: 2px 8px; border: 1px solid rgba(255,255,255,.18); }
.status-online { color: #00ffcc; }
.status-ok { color: #86efac; }
.status-warn { color: #fde68a; }
.status-error { color: #ff7777; }
.status-muted { color: var(--text-dim); }

.selected-box, .requirement-box, .warning-panel, .health-card {
  display: grid;
  gap: 7px;
  margin-bottom: 18px;
  padding: 16px;
  border-left: 3px solid var(--cyan);
  background: rgba(0, 242, 255, 0.06);
}
.requirement-box.blocked, .warning-panel, .health-error {
  border-left-color: #ff7777;
  background: rgba(255, 77, 77, 0.08);
}
.health-ok { border-left-color: #00ffcc; background: rgba(0, 255, 204, 0.06); }
.health-muted { border-left-color: rgba(255,255,255,.28); background: rgba(255, 255, 255, 0.04); }
.health-head { display: flex; justify-content: space-between; gap: 14px; align-items: flex-start; }
.health-badge { color: var(--cyan); font-family: "Courier New", monospace; font-size: 12px; border: 1px solid rgba(0,242,255,.3); padding: 3px 8px; }
.health-ok-text { color: #00ffcc; margin: 0; }
.issue-list { display: grid; gap: 8px; }
.issue-item { display: grid; gap: 4px; padding: 10px; border: 1px solid rgba(255, 119, 119, .3); background: rgba(255, 119, 119, .08); }
.issue-warn { border-color: rgba(253, 230, 138, .35); background: rgba(253, 230, 138, .08); }
.issue-error code { color: #ff7777; }
.issue-warn code { color: #fde68a; }
.selected-box label, .requirement-box label, .model-summary label, .binding-grid label, .field span, .health-card label {
  color: var(--text-dim);
  font-size: 11px;
  letter-spacing: 1px;
}

.form-grid, .model-summary, .binding-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.field { display: grid; gap: 8px; }
.field.full, .model-summary .full, .binding-grid .full { grid-column: span 2; }
select {
  width: 100%;
  box-sizing: border-box;
  color: var(--text-white);
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid var(--border-cyan);
  padding: 10px 12px;
  outline: none;
}
select:focus { border-color: var(--border-cyan-strong); }

.model-summary, .current-binding, .hint-panel, .raw-details { margin-top: 22px; }
.model-summary > div, .binding-grid > div {
  display: grid;
  gap: 7px;
  padding: 14px;
  background: rgba(0, 0, 0, 0.28);
  border: 1px solid rgba(0, 242, 255, 0.16);
}
code, pre {
  color: var(--cyan);
  font-family: "Courier New", monospace;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
pre { margin: 0; font-size: 12px; line-height: 1.6; }
.raw-details { border: 1px solid rgba(0,242,255,.18); padding: 12px; background: rgba(0,0,0,.24); }
.raw-details summary { cursor: pointer; color: var(--cyan); margin-bottom: 10px; }

.action-row { display: flex; justify-content: flex-end; gap: 14px; margin-top: 24px; }
.cyber-submit-btn, .cyber-button-outline, .danger-btn {
  border: 1px solid var(--cyan);
  color: var(--cyan);
  background: rgba(0, 242, 255, 0.05);
  padding: 10px 20px;
  cursor: pointer;
  font-weight: 800;
}
.cyber-submit-btn {
  color: #000;
  background: var(--cyan);
  clip-path: polygon(12px 0, 100% 0, calc(100% - 12px) 100%, 0 100%);
}
.danger-btn { border-color: rgba(255, 77, 77, 0.6); color: #ff7777; background: rgba(255, 77, 77, 0.08); }
button:disabled { opacity: 0.45; cursor: not-allowed; }

.error-banner, .success-banner {
  margin-bottom: 18px;
  padding: 12px;
  font-family: monospace;
  font-size: 13px;
}
.error-banner { color: #ff7777; border: 1px solid rgba(255, 77, 77, 0.35); background: rgba(255, 77, 77, 0.06); }
.success-banner { color: #00ffcc; border: 1px solid rgba(0, 255, 204, 0.35); background: rgba(0, 255, 204, 0.06); }
.empty { color: var(--text-dim); padding: 18px 0; }
.blink { animation: blink 1s infinite; font-weight: bold; margin-right: 8px; }
@keyframes blink { 50% { opacity: 0; } }

@media (max-width: 980px) {
  .layout-grid { grid-template-columns: 1fr; }
  .intro { flex-direction: column; align-items: flex-start; }
  .form-grid, .model-summary, .binding-grid { grid-template-columns: 1fr; }
  .field.full, .model-summary .full, .binding-grid .full { grid-column: span 1; }
}
</style>
