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
  <div class="dp-dashboard-container">
    
    <!-- 全局操作栏与标题 (仿大屏顶部) -->
    <header class="dp-header">
      <div class="dp-header-titles">
        <h1 class="dp-main-title">实例模型绑定与管控</h1>
        <p class="dp-sub-title">确保 family_fingerprint 一致性校验与运行期健康监控</p>
      </div>
      <div class="dp-header-actions">
        <button type="button" class="dp-btn-icon" :disabled="loading" @click="loadAll">
          <span>↻</span> 实时刷新
        </button>
        <button type="button" class="dp-btn-icon" :disabled="healthLoading || !selectedInstanceId" @click="loadHealth">
          <span>☤</span> 健康检查
        </button>
      </div>
    </header>

    <!-- 顶部消息通知栏 -->
    <div v-if="error" class="dp-alert dp-alert-error"><span class="blink">⚠</span> {{ error }}</div>
    <div v-if="message" class="dp-alert dp-alert-success"><span class="blink">✔</span> {{ message }}</div>

    <div class="dp-layout-grid">
      
      <!-- 左侧：实例列表面板 -->
      <aside class="dp-panel dp-col-left">
        <div class="dp-panel-title">[ 插件实例列表 ]</div>
        <div class="dp-instance-list">
          <button
            v-for="item in instances"
            :key="item.id"
            type="button"
            class="dp-instance-item"
            :class="{ active: selectedInstanceId === item.id }"
            @click="selectedInstanceId = item.id"
          >
            <div class="item-main">
              <span class="item-name">{{ item.name }}</span>
              <span class="item-status" :class="statusClass(item.status)">
                <i class="status-dot"></i>{{ item.status }}
              </span>
            </div>
            <div class="item-meta">{{ item.package_name }}@{{ item.version }}</div>
          </button>
          <div v-if="!instances.length && !loading" class="dp-empty-state">当前集群暂无排队或冲突任务，且无实例数据</div>
        </div>
      </aside>

      <!-- 右侧：详情与配置管控面板 -->
      <main class="dp-col-right">
        
        <!-- 上半部分两列：基础信息 & 健康状态 -->
        <div class="dp-inner-grid-2">
          
          <!-- 基础运行信息与插件要求 -->
          <section class="dp-panel">
            <div class="dp-panel-title">[ 基础运行信息 ]</div>
            <div class="dp-kv-list" v-if="selectedInstance">
              <div class="dp-kv-row">
                <span class="dp-kv-label">当前实例</span>
                <span class="dp-kv-value highlight-cyan">{{ selectedInstance.name }}</span>
              </div>
              <div class="dp-kv-row">
                <span class="dp-kv-label">插件版本</span>
                <span class="dp-kv-value">{{ selectedInstance.package_name }}@{{ selectedInstance.version }}</span>
              </div>
              <div class="dp-kv-row">
                <span class="dp-kv-label">声明的模型指纹</span>
                <span class="dp-kv-value highlight-code" v-if="requiredFingerprint">{{ requiredFingerprint }}</span>
                <span class="dp-kv-value dp-text-error" v-else>未声明依赖，禁止绑定</span>
              </div>
              <div class="dp-kv-row" v-if="!requiredFingerprint">
                <span class="dp-kv-label">指纹读取状态</span>
                <span class="dp-kv-value dp-text-muted">{{ requirement?.message || '尚未读取' }}</span>
              </div>
            </div>
            <div v-else class="dp-empty-state">请在左侧选择实例</div>
          </section>

          <!-- 健康状态面板 -->
          <section class="dp-panel">
            <div class="dp-panel-title">[ 集群任务锁状态 / 健康度 ]</div>
            <div class="dp-health-board" :class="healthStatusClass">
              <div class="health-header">
                <div class="health-title">{{ healthTitle }}</div>
                <div class="health-badge">{{ healthLoading ? 'CHECKING...' : (health?.status || 'UNKNOWN') }}</div>
              </div>
              
              <div class="health-body">
                <p v-if="health?.healthy" class="health-ok-text">
                  <span class="icon-check">✔</span> 运行前模型绑定校验已通过。
                </p>
                
                <div v-if="health?.errors?.length" class="dp-issue-box">
                  <div v-for="item in health.errors" :key="`${item.code}:${item.message}`" class="issue-item issue-error">
                    <span class="issue-code">{{ item.code }}</span>
                    <span class="issue-msg">{{ item.message }}</span>
                  </div>
                </div>
                
                <div v-if="health?.warnings?.length" class="dp-issue-box">
                  <div v-for="item in health.warnings" :key="`${item.code}:${item.message}`" class="issue-item issue-warn">
                    <span class="issue-code">{{ item.code }}</span>
                    <span class="issue-msg">{{ item.message }}</span>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>

        <!-- 中间：核心绑定配置 -->
        <section class="dp-panel dp-mt-4">
          <div class="dp-panel-title">[ 模型调度与绑定配置 ]</div>
          
          <div v-if="requiredFingerprint && compatibleModels.length === 0" class="dp-alert dp-alert-warn dp-mb-4">
            系统未匹配到指纹为 {{ requiredFingerprint }} 的模型。请上传对应模型包。
          </div>

          <div class="dp-form-row">
            <div class="dp-form-group">
              <label class="dp-form-label">兼容模型分配</label>
              <div class="dp-select-wrapper">
                <select v-model.number="selectedModelId" :disabled="!requiredFingerprint" class="dp-select">
                  <option :value="null">-- 等待分配 --</option>
                  <option v-for="model in compatibleModels" :key="model.id" :value="model.id">
                    {{ model.display_name || model.model_name }} [Active: {{ model.active_version || '未上线' }}]
                  </option>
                </select>
              </div>
            </div>

            <div class="dp-form-group">
              <label class="dp-form-label">版本调度策略</label>
              <div class="dp-select-wrapper">
                <select v-model="bindingMode" :disabled="!requiredFingerprint" class="dp-select">
                  <option value="current">动态跟随 Active 版本</option>
                  <option value="fixed_version">静态锁定特定版本</option>
                </select>
              </div>
            </div>

            <div class="dp-form-group" v-if="bindingMode === 'fixed_version'">
              <label class="dp-form-label">锁定版本号</label>
              <div class="dp-select-wrapper">
                <select v-model.number="selectedVersionId" class="dp-select">
                  <option :value="null">-- 选择固定版本 --</option>
                  <option v-for="version in versions" :key="version.id" :value="version.id">
                    v{{ version.version }} ({{ version.status }})
                  </option>
                </select>
              </div>
            </div>
          </div>
          
          <div class="dp-action-bar">
            <button type="button" class="dp-btn dp-btn-danger" :disabled="saving || !currentBinding" @click="clearBinding">
              <span class="icon">⊘</span> 强制解除绑定
            </button>
            <button type="button" class="dp-btn dp-btn-primary" :disabled="saving || !canBind" @click="submitBinding">
              <span class="icon">⎘</span> {{ saving ? '系统执行中...' : '提交策略生效' }}
            </button>
          </div>
        </section>

        <!-- 底部两列：模型详细信息与当前绑定快照 -->
        <div class="dp-inner-grid-2 dp-mt-4">
          <section class="dp-panel">
            <div class="dp-panel-title">[ 目标模型信息快照 ]</div>
            <div class="dp-kv-list" v-if="selectedModel">
              <div class="dp-kv-row">
                <span class="dp-kv-label">模型标识</span>
                <span class="dp-kv-value">{{ selectedModel.model_name }}</span>
              </div>
              <div class="dp-kv-row">
                <span class="dp-kv-label">Active 状态码</span>
                <span class="dp-kv-value highlight-cyan">{{ activeVersionLabel }}</span>
              </div>
              <div class="dp-kv-row">
                <span class="dp-kv-label">指纹校验码 (Fingerprint)</span>
                <span class="dp-kv-value highlight-code">{{ selectedModel.family_fingerprint }}</span>
              </div>
              <div class="dp-kv-row">
                <span class="dp-kv-label">系统运行状态</span>
                <span class="dp-kv-value" :class="statusClass(selectedModel.status)">{{ selectedModel.status }}</span>
              </div>
            </div>
            <div v-else class="dp-empty-state">待选定目标模型</div>
          </section>

          <section class="dp-panel">
            <div class="dp-panel-title">[ 实时任务执行流水 (当前绑定) ]</div>
            <div class="dp-kv-list" v-if="currentBinding">
              <div class="dp-kv-row">
                <span class="dp-kv-label">绑定模型</span>
                <span class="dp-kv-value">{{ currentBinding.model_name }}</span>
              </div>
              <div class="dp-kv-row">
                <span class="dp-kv-label">运行模式</span>
                <span class="dp-kv-value">{{ currentBinding.binding_mode }}</span>
              </div>
              <div class="dp-kv-row">
                <span class="dp-kv-label">锁定版本 ID</span>
                <span class="dp-kv-value">{{ currentBinding.model_version_id ?? '动态跟随 (NULL)' }}</span>
              </div>
              <div class="dp-kv-row">
                <span class="dp-kv-label">指纹一致性监测</span>
                <span class="dp-kv-value" :class="currentBinding.fingerprint_match ? 'status-online' : 'status-warn'">
                  {{ currentBinding.fingerprint_match ? '● 校验通过 (MATCH)' : '▲ 异常 (MISMATCH)' }}
                </span>
              </div>
            </div>
            <div v-else class="dp-empty-state">当前节点无排队或绑定策略</div>
          </section>
        </div>

        <!-- 隐藏的调试信息 -->
        <details v-if="health" class="dp-raw-details dp-mt-4">
          <summary>[ 展开终端调试日志 (Raw Health Data) ]</summary>
          <pre>{{ stringify(health) }}</pre>
        </details>

      </main>
    </div>
  </div>
</template>

<style scoped>
/* =========================================
   赛博工业大屏 主题变量设定 (参考提供图像)
   ========================================= */
.dp-dashboard-container {
  --dp-bg-base: #010A14;        /* 极暗蓝底色 */
  --dp-bg-panel: rgba(2, 17, 34, 0.75); /* 面板半透明底色 */
  --dp-cyan-main: #00F2FE;      /* 主亮青色 */
  --dp-cyan-dark: rgba(0, 242, 254, 0.2); 
  --dp-cyan-border: rgba(0, 242, 254, 0.35);
  
  --dp-text-main: #E5EAF3;      /* 主文本色 */
  --dp-text-label: #6B8B9E;     /* 柔和的标签灰蓝色 */
  --dp-text-muted: #4B6373;
  
  --dp-color-success: #00FFB2;  /* 成功绿 */
  --dp-color-warn: #FDB100;     /* 警告黄 */
  --dp-color-error: #FF4D4F;    /* 错误红 */

  min-height: 100vh;
  padding: 24px;
  background-color: var(--dp-bg-base);
  /* 工业网格背景 */
  background-image: 
    linear-gradient(rgba(0, 242, 254, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 242, 254, 0.04) 1px, transparent 1px);
  background-size: 40px 40px;
  color: var(--dp-text-main);
  font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
  box-sizing: border-box;
}

*, *::before, *::after { box-sizing: inherit; }

/* 工具类 */
.dp-mt-4 { margin-top: 20px; }
.dp-mb-4 { margin-bottom: 20px; }
.highlight-cyan { color: var(--dp-cyan-main); font-weight: bold; }
.highlight-code { color: var(--dp-color-warn); font-family: "Courier New", monospace; }
.dp-text-muted { color: var(--dp-text-muted); }
.dp-text-error { color: var(--dp-color-error); }

/* =========================================
   头部栏 (图顶部的标题与按钮)
   ========================================= */
.dp-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 20px;
  margin-bottom: 24px;
  border-bottom: 1px solid var(--dp-cyan-border);
  position: relative;
}
.dp-header::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 0;
  width: 120px;
  height: 2px;
  background: var(--dp-cyan-main);
  box-shadow: 0 0 10px var(--dp-cyan-main);
}
.dp-main-title {
  margin: 0;
  font-size: 24px;
  color: var(--dp-cyan-main);
  letter-spacing: 2px;
  font-weight: 600;
  text-shadow: 0 0 8px rgba(0, 242, 254, 0.4);
}
.dp-sub-title {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--dp-text-label);
  letter-spacing: 1px;
}
.dp-header-actions { display: flex; gap: 12px; }

/* 头部小按钮 */
.dp-btn-icon {
  background: transparent;
  border: 1px solid var(--dp-cyan-border);
  color: var(--dp-cyan-main);
  padding: 6px 16px;
  font-size: 13px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s;
  border-radius: 2px;
}
.dp-btn-icon:hover:not(:disabled) {
  background: var(--dp-cyan-dark);
  border-color: var(--dp-cyan-main);
  box-shadow: 0 0 8px var(--dp-cyan-dark);
}
.dp-btn-icon:disabled { opacity: 0.5; cursor: not-allowed; border-color: var(--dp-text-muted); color: var(--dp-text-muted); }

/* =========================================
   通知横幅 (Alerts)
   ========================================= */
.dp-alert {
  padding: 10px 16px;
  margin-bottom: 20px;
  font-size: 13px;
  display: flex;
  align-items: center;
  border-left: 3px solid transparent;
  background: rgba(0,0,0,0.4);
}
.dp-alert-error { border-color: var(--dp-color-error); color: var(--dp-color-error); background: rgba(255, 77, 79, 0.1); }
.dp-alert-success { border-color: var(--dp-color-success); color: var(--dp-color-success); background: rgba(0, 255, 178, 0.1); }
.dp-alert-warn { border-color: var(--dp-color-warn); color: var(--dp-color-warn); background: rgba(253, 177, 0, 0.1); }
.blink { animation: dp-blink 1.5s infinite; margin-right: 8px; }
@keyframes dp-blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

/* =========================================
   网格与面板基础 (Panel Widgets)
   ========================================= */
.dp-layout-grid {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 24px;
  align-items: start;
}
.dp-inner-grid-2 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 24px;
}

.dp-panel {
  background: var(--dp-bg-panel);
  border: 1px solid var(--dp-cyan-border);
  padding: 20px;
  position: relative;
  /* 类似大屏组件的角部高亮 */
  box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.5);
}
.dp-panel::before {
  content: '';
  position: absolute;
  top: -1px; left: -1px;
  width: 10px; height: 10px;
  border-top: 2px solid var(--dp-cyan-main);
  border-left: 2px solid var(--dp-cyan-main);
}
.dp-panel::after {
  content: '';
  position: absolute;
  bottom: -1px; right: -1px;
  width: 10px; height: 10px;
  border-bottom: 2px solid var(--dp-cyan-main);
  border-right: 2px solid var(--dp-cyan-main);
}

.dp-panel-title {
  font-size: 14px;
  color: var(--dp-cyan-main);
  font-weight: bold;
  margin-bottom: 16px;
  letter-spacing: 1px;
}

.dp-empty-state {
  color: var(--dp-text-muted);
  text-align: center;
  padding: 30px 0;
  font-size: 13px;
  letter-spacing: 1px;
}

/* =========================================
   左侧：实例列表
   ========================================= */
.dp-instance-list { display: flex; flex-direction: column; gap: 8px; }
.dp-instance-item {
  width: 100%;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(107, 139, 158, 0.3);
  padding: 12px;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s;
  color: var(--dp-text-main);
}
.dp-instance-item:hover { border-color: var(--dp-cyan-border); background: rgba(0, 242, 254, 0.05); }
.dp-instance-item.active {
  border-color: var(--dp-cyan-main);
  background: var(--dp-cyan-dark);
  box-shadow: inset 0 0 10px rgba(0, 242, 254, 0.1);
}
.item-main { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.item-name { font-weight: bold; font-size: 14px; }
.item-meta { font-size: 12px; color: var(--dp-text-label); }
.item-status { font-size: 12px; display: flex; align-items: center; gap: 4px; }
.status-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }

/* 状态颜色 */
.status-online { color: var(--dp-color-success); }
.status-online .status-dot { background: var(--dp-color-success); box-shadow: 0 0 5px var(--dp-color-success); }
.status-ok { color: var(--dp-cyan-main); }
.status-ok .status-dot { background: var(--dp-cyan-main); }
.status-warn { color: var(--dp-color-warn); }
.status-warn .status-dot { background: var(--dp-color-warn); }
.status-error { color: var(--dp-color-error); }
.status-error .status-dot { background: var(--dp-color-error); }
.status-muted { color: var(--dp-text-muted); }
.status-muted .status-dot { background: var(--dp-text-muted); }

/* =========================================
   右侧：键值对数据表 (参考图"基础运行信息")
   ========================================= */
.dp-kv-list { display: flex; flex-direction: column; }
.dp-kv-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  font-size: 13px;
}
.dp-kv-row:last-child { border-bottom: none; }
.dp-kv-label { color: var(--dp-text-label); }
.dp-kv-value { color: var(--dp-text-main); text-align: right; word-break: break-all; max-width: 65%; }

/* =========================================
   健康状态面板
   ========================================= */
.dp-health-board { padding: 14px; border: 1px solid transparent; background: rgba(0,0,0,0.2); }
.dp-health-board.health-ok { border-color: rgba(0, 255, 178, 0.3); }
.dp-health-board.health-error { border-color: rgba(255, 77, 79, 0.3); background: rgba(255, 77, 79, 0.05); }
.dp-health-board.health-muted { border-color: rgba(255, 255, 255, 0.1); }

.health-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 10px; margin-bottom: 10px; }
.health-title { font-weight: bold; font-size: 14px; }
.health-badge { font-family: monospace; font-size: 12px; padding: 2px 6px; background: rgba(255,255,255,0.1); border-radius: 2px; }

.health-ok .health-title { color: var(--dp-color-success); }
.health-error .health-title { color: var(--dp-color-error); }
.health-ok .health-badge { color: var(--dp-color-success); border: 1px solid var(--dp-color-success); }
.health-error .health-badge { color: var(--dp-color-error); border: 1px solid var(--dp-color-error); }

.health-ok-text { color: var(--dp-color-success); font-size: 13px; margin: 0; }

.dp-issue-box { display: flex; flex-direction: column; gap: 8px; margin-top: 10px; }
.issue-item { display: flex; flex-direction: column; padding: 8px 10px; font-size: 12px; border-left: 2px solid; background: rgba(0,0,0,0.3); }
.issue-error { border-left-color: var(--dp-color-error); }
.issue-warn { border-left-color: var(--dp-color-warn); }
.issue-code { font-family: monospace; color: var(--dp-text-label); margin-bottom: 4px; }
.issue-error .issue-code { color: var(--dp-color-error); }
.issue-warn .issue-code { color: var(--dp-color-warn); }
.issue-msg { color: var(--dp-text-main); }

/* =========================================
   表单与操作区
   ========================================= */
.dp-form-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 20px; }
.dp-form-group { display: flex; flex-direction: column; gap: 8px; }
.dp-form-label { color: var(--dp-text-label); font-size: 12px; }
.dp-select-wrapper { position: relative; }
.dp-select {
  width: 100%;
  appearance: none;
  background: #030F1A;
  border: 1px solid var(--dp-cyan-border);
  color: var(--dp-text-main);
  padding: 10px 12px;
  font-size: 13px;
  outline: none;
  cursor: pointer;
  transition: border-color 0.2s;
}
.dp-select:focus { border-color: var(--dp-cyan-main); box-shadow: 0 0 5px var(--dp-cyan-dark); }
.dp-select:disabled { opacity: 0.5; cursor: not-allowed; background: rgba(0,0,0,0.5); }
/* 自定义下拉箭头 */
.dp-select-wrapper::after {
  content: '▼';
  font-size: 10px;
  color: var(--dp-cyan-main);
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  pointer-events: none;
}

.dp-action-bar { display: flex; justify-content: flex-end; gap: 16px; border-top: 1px dashed rgba(0, 242, 254, 0.2); padding-top: 20px; }
.dp-btn {
  padding: 10px 24px;
  font-size: 14px;
  font-weight: bold;
  cursor: pointer;
  border: 1px solid transparent;
  display: flex; align-items: center; gap: 8px;
  transition: all 0.2s;
  letter-spacing: 1px;
}
.dp-btn:disabled { opacity: 0.4; cursor: not-allowed; filter: grayscale(1); }

.dp-btn-primary {
  background: rgba(0, 242, 254, 0.1);
  border-color: var(--dp-cyan-main);
  color: var(--dp-cyan-main);
}
.dp-btn-primary:hover:not(:disabled) {
  background: var(--dp-cyan-main);
  color: var(--dp-bg-base);
  box-shadow: 0 0 15px var(--dp-cyan-dark);
}

.dp-btn-danger {
  background: rgba(255, 77, 79, 0.05);
  border-color: rgba(255, 77, 79, 0.5);
  color: var(--dp-color-error);
}
.dp-btn-danger:hover:not(:disabled) {
  background: rgba(255, 77, 79, 0.2);
  border-color: var(--dp-color-error);
}

/* =========================================
   其他细节 (代码与日志展开)
   ========================================= */
.dp-raw-details {
  background: rgba(0,0,0,0.4);
  border: 1px solid var(--dp-text-muted);
  padding: 12px;
}
.dp-raw-details summary {
  color: var(--dp-text-label);
  font-size: 12px;
  cursor: pointer;
  outline: none;
}
.dp-raw-details pre {
  margin: 10px 0 0;
  color: var(--dp-color-warn);
  font-size: 12px;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: monospace;
}

/* 响应式降级 */
@media (max-width: 1100px) {
  .dp-layout-grid { grid-template-columns: 260px 1fr; }
  .dp-inner-grid-2 { grid-template-columns: 1fr; gap: 16px; }
}
@media (max-width: 850px) {
  .dp-layout-grid { grid-template-columns: 1fr; }
  .dp-col-left { max-height: 300px; overflow-y: auto; }
}
</style>