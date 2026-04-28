<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  getMaintenanceStatus,
  getSystemSettings,
  runDatabaseCleanup,
  runRunDirectoryCleanup,
  updateSystemSettings,
  type MaintenanceStatus,
  type SettingCatalogItem,
  type SystemSettingsPayload,
} from '../api/systemSettings'

const loading = ref(false)
const saving = ref(false)
const error = ref('')
const message = ref('')
const settingsFile = ref('')
const catalog = ref<SettingCatalogItem[]>([])
const status = ref<MaintenanceStatus | null>(null)
const form = reactive<SystemSettingsPayload>({
  maintenance: {
    run_directory_cleanup: {},
    database_cleanup: {},
  },
})

const editableItems = computed(() => catalog.value.filter((item) => item.editable))
const readonlyItems = computed(() => catalog.value.filter((item) => !item.editable))
const runDirItems = computed(() => editableItems.value.filter((item) => item.path.startsWith('maintenance.run_directory_cleanup.')))
const dbItems = computed(() => editableItems.value.filter((item) => item.path.startsWith('maintenance.database_cleanup.')))
const runtimeReadonly = computed(() => readonlyItems.value)

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value))
}

function getNested(payload: Record<string, any>, path: string) {
  return path.split('.').reduce((cursor: any, key) => (cursor == null ? undefined : cursor[key]), payload)
}

function setNested(payload: Record<string, any>, path: string, value: unknown) {
  const parts = path.split('.')
  let cursor: any = payload
  for (const key of parts.slice(0, -1)) {
    if (!cursor[key] || typeof cursor[key] !== 'object') cursor[key] = {}
    cursor = cursor[key]
  }
  cursor[parts[parts.length - 1]] = value
}

function inputValue(path: string) {
  return getNested(form, path)
}

function updateValue(item: SettingCatalogItem, raw: Event) {
  const target = raw.target as HTMLInputElement
  let value: unknown
  if (item.type === 'bool') value = target.checked
  else if (item.type === 'int') value = Number.parseInt(target.value || '0', 10)
  else if (item.type === 'float') value = Number.parseFloat(target.value || '0')
  else value = target.value
  setNested(form, item.path, value)
}

async function loadAll() {
  loading.value = true
  error.value = ''
  message.value = ''
  try {
    const payload = await getSystemSettings()
    settingsFile.value = payload.catalog.settings_file
    catalog.value = payload.catalog.items
    Object.assign(form, deepClone(payload.settings))
    status.value = await getMaintenanceStatus()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '系统设置加载失败'
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  saving.value = true
  error.value = ''
  message.value = ''
  try {
    const payload = await updateSystemSettings(deepClone(form))
    settingsFile.value = payload.catalog.settings_file
    catalog.value = payload.catalog.items
    Object.assign(form, deepClone(payload.settings))
    message.value = '系统设置已保存，维护任务会在下一轮清理周期读取新配置。'
  } catch (err) {
    error.value = err instanceof Error ? err.message : '系统设置保存失败'
  } finally {
    saving.value = false
  }
}

async function runCleanup(kind: 'runs' | 'db', dryRun: boolean) {
  saving.value = true
  error.value = ''
  message.value = ''
  try {
    const report = kind === 'runs' ? await runRunDirectoryCleanup(dryRun) : await runDatabaseCleanup(dryRun)
    message.value = `${kind === 'runs' ? 'runs 目录清理' : '数据库清理'}已执行：${JSON.stringify(report)}`
    status.value = await getMaintenanceStatus()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '清理任务执行失败'
  } finally {
    saving.value = false
  }
}

function formatValue(value: unknown) {
  if (value == null || value === '') return '-'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

onMounted(loadAll)
</script>

<template>
  <div class="dp-dashboard-container">
    
    <!-- 全局操作栏与标题 -->
    <header class="dp-header">
      <div class="dp-header-titles">
        <h1 class="dp-main-title">系统维护与策略设置</h1>
        <p class="dp-sub-title">集中管理维护类运行时配置。高风险系统配置仅作数据下发只读展示。</p>
      </div>
      <div class="dp-header-actions">
        <button type="button" class="dp-btn-icon" :disabled="loading" @click="loadAll">
          <span>↻</span> 数据重载
        </button>
        <button type="button" class="dp-btn-primary" :disabled="saving || loading" @click="saveSettings">
          <span>⎘</span> 下发保存设置
        </button>
      </div>
    </header>

    <!-- 告警与通知 -->
    <div v-if="error" class="dp-alert dp-alert-error"><span class="blink">⚠</span> ERROR: {{ error }}</div>
    <div v-if="message" class="dp-alert dp-alert-success"><span class="blink">✔</span> SUCCESS: {{ message }}</div>

    <!-- 顶部状态栏 -->
    <div class="dp-meta-strip">
      <span class="dp-meta-label">当前活跃配置域文件 (Settings File) :</span>
      <span class="dp-meta-value">{{ settingsFile || '加载中...' }}</span>
    </div>

    <!-- 核心布局：双列清理配置 -->
    <div class="dp-layout-grid-2 dp-mt-4">
      
      <!-- 模块 1：runs 目录清理 -->
      <article class="dp-panel">
        <div class="dp-panel-title">[ 运行时缓存目录清理策略 ]</div>
        <div class="dp-panel-subtitle">Target Dir: <span class="highlight-cyan">var/runs/run-*</span></div>
        
        <div class="dp-form-list">
          <label v-for="item in runDirItems" :key="item.path" class="dp-field-row">
            <div class="field-info">
              <span class="field-label">{{ item.label }}</span>
              <span class="field-desc">{{ item.description }}</span>
            </div>
            <div class="field-input">
              <input
                v-if="item.type === 'bool'"
                type="checkbox"
                class="dp-checkbox"
                :checked="Boolean(inputValue(item.path))"
                @change="updateValue(item, $event)"
              />
              <input
                v-else
                class="dp-input"
                :type="item.type === 'str' ? 'text' : 'number'"
                :min="item.minimum ?? undefined"
                :max="item.maximum ?? undefined"
                :value="inputValue(item.path)"
                @input="updateValue(item, $event)"
              />
            </div>
          </label>
        </div>

        <div class="dp-action-bar">
          <button class="dp-btn dp-btn-ghost" :disabled="saving" @click="runCleanup('runs', true)">
            <span>⚗</span> 模拟演练 (Dry Run)
          </button>
          <button class="dp-btn dp-btn-danger" :disabled="saving" @click="runCleanup('runs', false)">
            <span>⚡</span> 强制执行清理
          </button>
        </div>

        <div class="dp-terminal">
          <div class="dp-terminal-header">>&nbsp;Task_Output: [ Runs_Cleanup_Report ]</div>
          <pre class="dp-terminal-body">{{ JSON.stringify(status?.run_directory_cleanup || {}, null, 2) }}</pre>
        </div>
      </article>

      <!-- 模块 2：数据库历史记录清理 -->
      <article class="dp-panel">
        <div class="dp-panel-title">[ 数据库历史游标与归档清理 ]</div>
        <div class="dp-panel-subtitle">Target Tables: <span class="highlight-cyan">plugin_runs / run_logs / audit_events</span></div>
        
        <div class="dp-form-list">
          <label v-for="item in dbItems" :key="item.path" class="dp-field-row">
            <div class="field-info">
              <span class="field-label">{{ item.label }}</span>
              <span class="field-desc">{{ item.description }}</span>
            </div>
            <div class="field-input">
              <input
                v-if="item.type === 'bool'"
                type="checkbox"
                class="dp-checkbox"
                :checked="Boolean(inputValue(item.path))"
                @change="updateValue(item, $event)"
              />
              <input
                v-else
                class="dp-input"
                :type="item.type === 'str' ? 'text' : 'number'"
                :min="item.minimum ?? undefined"
                :max="item.maximum ?? undefined"
                :value="inputValue(item.path)"
                @input="updateValue(item, $event)"
              />
            </div>
          </label>
        </div>

        <div class="dp-action-bar">
          <button class="dp-btn dp-btn-ghost" :disabled="saving" @click="runCleanup('db', true)">
            <span>⚗</span> 模拟演练 (Dry Run)
          </button>
          <button class="dp-btn dp-btn-danger" :disabled="saving" @click="runCleanup('db', false)">
            <span>⚡</span> 强制执行清理
          </button>
        </div>

        <div class="dp-terminal">
          <div class="dp-terminal-header">>&nbsp;Task_Output: [ DB_Cleanup_Report ]</div>
          <pre class="dp-terminal-body">{{ JSON.stringify(status?.database_cleanup || {}, null, 2) }}</pre>
        </div>
      </article>
    </div>

    <!-- 模块 3：静态配置 (只读) -->
    <article class="dp-panel dp-mt-4">
      <div class="dp-panel-title">[ 静态系统配置扫描矩阵 ]</div>
      <div class="dp-panel-subtitle dp-text-warn">※ 当前状态：READ_ONLY | 配置应由底层环境变量或 config/platform.yaml 覆盖接管。</div>
      
      <div class="dp-readonly-grid">
        <div v-for="item in runtimeReadonly" :key="item.path" class="dp-readonly-card">
          <div class="ro-label">{{ item.label }}</div>
          <div class="ro-value" :title="formatValue(item.value)">{{ formatValue(item.value) }}</div>
          <div class="ro-path">{{ item.path }}</div>
        </div>
      </div>
    </article>

  </div>
</template>

<style scoped>
/* =========================================
   赛博工业大屏 主题与基础变量
   ========================================= */
.dp-dashboard-container {
  --dp-bg-base: #010A14;        
  --dp-bg-panel: rgba(2, 17, 34, 0.75); 
  --dp-cyan-main: #00F2FE;      
  --dp-cyan-dark: rgba(0, 242, 254, 0.15); 
  --dp-cyan-border: rgba(0, 242, 254, 0.35);
  
  --dp-text-main: #E5EAF3;      
  --dp-text-label: #6B8B9E;     
  --dp-text-muted: #4B6373;
  
  --dp-color-success: #00FFB2;  
  --dp-color-warn: #FDB100;     
  --dp-color-error: #FF4D4F;    

  min-height: 100vh;
  padding: 24px;
  background-color: var(--dp-bg-base);
  background-image: 
    linear-gradient(rgba(0, 242, 254, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 242, 254, 0.03) 1px, transparent 1px);
  background-size: 30px 30px;
  color: var(--dp-text-main);
  font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
  box-sizing: border-box;
}

*, *::before, *::after { box-sizing: inherit; }

.dp-mt-4 { margin-top: 24px; }
.highlight-cyan { color: var(--dp-cyan-main); font-family: monospace; }
.dp-text-warn { color: var(--dp-color-warn); font-size: 12px; }

/* =========================================
   头部与通知区域
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
  content: ''; position: absolute; bottom: -1px; left: 0;
  width: 120px; height: 2px;
  background: var(--dp-cyan-main); box-shadow: 0 0 10px var(--dp-cyan-main);
}
.dp-main-title { margin: 0; font-size: 24px; color: var(--dp-cyan-main); letter-spacing: 2px; text-shadow: 0 0 8px rgba(0, 242, 254, 0.4); }
.dp-sub-title { margin: 6px 0 0; font-size: 13px; color: var(--dp-text-label); }

.dp-header-actions { display: flex; gap: 12px; }
.dp-btn-icon, .dp-btn-primary {
  padding: 8px 18px;
  font-size: 13px; font-weight: bold;
  cursor: pointer; display: flex; align-items: center; gap: 6px;
  transition: all 0.2s; border-radius: 2px;
}
.dp-btn-icon {
  background: transparent; border: 1px solid var(--dp-cyan-border); color: var(--dp-cyan-main);
}
.dp-btn-icon:hover:not(:disabled) { background: var(--dp-cyan-dark); box-shadow: 0 0 8px var(--dp-cyan-dark); }
.dp-btn-primary {
  background: var(--dp-cyan-main); border: 1px solid var(--dp-cyan-main); color: #000;
}
.dp-btn-primary:hover:not(:disabled) { box-shadow: 0 0 15px var(--dp-cyan-dark); opacity: 0.9; }
button:disabled { opacity: 0.4; cursor: not-allowed; filter: grayscale(1); }

.dp-alert { padding: 10px 16px; margin-bottom: 20px; font-size: 13px; border-left: 3px solid; background: rgba(0,0,0,0.4); }
.dp-alert-error { border-color: var(--dp-color-error); color: var(--dp-color-error); background: rgba(255, 77, 79, 0.1); }
.dp-alert-success { border-color: var(--dp-color-success); color: var(--dp-color-success); background: rgba(0, 255, 178, 0.1); }
.blink { animation: dp-blink 1.5s infinite; margin-right: 8px; font-weight: bold; }
@keyframes dp-blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

/* 信息条 */
.dp-meta-strip {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 16px; margin-bottom: 24px;
  background: rgba(0, 242, 254, 0.05);
  border: 1px solid var(--dp-cyan-border);
  border-left: 4px solid var(--dp-cyan-main);
}
.dp-meta-label { color: var(--dp-text-label); font-size: 13px; }
.dp-meta-value { color: var(--dp-cyan-main); font-family: monospace; font-size: 14px; }

/* =========================================
   网格与面板组件
   ========================================= */
.dp-layout-grid-2 {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(480px, 1fr));
  gap: 24px;
}
.dp-panel {
  background: var(--dp-bg-panel);
  border: 1px solid var(--dp-cyan-border);
  padding: 24px; position: relative;
  box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.4);
}
.dp-panel::before {
  content: ''; position: absolute; top: -1px; left: -1px; width: 12px; height: 12px;
  border-top: 2px solid var(--dp-cyan-main); border-left: 2px solid var(--dp-cyan-main);
}
.dp-panel::after {
  content: ''; position: absolute; bottom: -1px; right: -1px; width: 12px; height: 12px;
  border-bottom: 2px solid var(--dp-cyan-main); border-right: 2px solid var(--dp-cyan-main);
}
.dp-panel-title { font-size: 15px; color: var(--dp-cyan-main); font-weight: bold; margin-bottom: 6px; letter-spacing: 1px; }
.dp-panel-subtitle { font-size: 12px; color: var(--dp-text-label); margin-bottom: 20px; }

/* =========================================
   表单列表与工业化控件
   ========================================= */
.dp-form-list { display: flex; flex-direction: column; gap: 12px; margin-bottom: 24px; }
.dp-field-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px;
  background: rgba(0,0,0,0.4);
  border: 1px solid rgba(107, 139, 158, 0.2);
  transition: border-color 0.2s;
}
.dp-field-row:hover { border-color: var(--dp-cyan-border); }
.field-info { display: flex; flex-direction: column; gap: 4px; max-width: 65%; }
.field-label { font-size: 14px; color: var(--dp-text-main); font-weight: bold; }
.field-desc { font-size: 11px; color: var(--dp-text-muted); }
.field-input { width: 160px; display: flex; justify-content: flex-end; }

/* 赛博风输入框 */
.dp-input {
  width: 100%;
  background: rgba(0,0,0,0.6);
  border: 1px solid var(--dp-cyan-border);
  color: var(--dp-cyan-main);
  padding: 8px 12px;
  font-family: monospace; font-size: 14px;
  outline: none; transition: all 0.3s;
}
.dp-input:focus { border-color: var(--dp-cyan-main); box-shadow: 0 0 10px var(--dp-cyan-dark); }

/* 赛博风复选框 */
.dp-checkbox {
  appearance: none;
  width: 24px; height: 24px;
  background: rgba(0,0,0,0.6);
  border: 1px solid var(--dp-cyan-border);
  cursor: pointer; position: relative;
  transition: all 0.2s;
}
.dp-checkbox:checked {
  background: var(--dp-cyan-dark);
  border-color: var(--dp-cyan-main);
  box-shadow: 0 0 8px var(--dp-cyan-dark);
}
.dp-checkbox:checked::after {
  content: '✔';
  position: absolute; top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  color: var(--dp-cyan-main); font-size: 14px;
}

/* =========================================
   卡片内操作按钮
   ========================================= */
.dp-action-bar { display: flex; justify-content: flex-end; gap: 12px; margin-bottom: 20px; border-top: 1px dashed rgba(107, 139, 158, 0.3); padding-top: 20px; }
.dp-btn {
  padding: 8px 16px; font-size: 13px; font-weight: bold; cursor: pointer;
  display: flex; align-items: center; gap: 6px; border: 1px solid transparent; transition: all 0.2s;
}
.dp-btn-ghost { background: rgba(0, 242, 254, 0.05); border-color: var(--dp-cyan-border); color: var(--dp-cyan-main); }
.dp-btn-ghost:hover:not(:disabled) { background: var(--dp-cyan-dark); }
.dp-btn-danger { background: rgba(255, 77, 79, 0.05); border-color: rgba(255, 77, 79, 0.5); color: var(--dp-color-error); }
.dp-btn-danger:hover:not(:disabled) { background: rgba(255, 77, 79, 0.2); }

/* =========================================
   终端输出窗口 (Terminal Logs)
   ========================================= */
.dp-terminal {
  background: #02070D;
  border: 1px solid rgba(107, 139, 158, 0.4);
  border-radius: 2px;
}
.dp-terminal-header {
  padding: 6px 12px;
  background: rgba(255,255,255,0.05);
  border-bottom: 1px solid rgba(107, 139, 158, 0.3);
  font-family: monospace; font-size: 11px; color: var(--dp-text-muted);
}
.dp-terminal-body {
  margin: 0; padding: 12px;
  font-family: "Courier New", monospace; font-size: 12px;
  color: var(--dp-color-success);
  min-height: 80px; max-height: 180px; overflow-y: auto;
  white-space: pre-wrap; word-break: break-all;
}
/* 终端滚动条优化 */
.dp-terminal-body::-webkit-scrollbar { width: 6px; }
.dp-terminal-body::-webkit-scrollbar-thumb { background: var(--dp-text-muted); border-radius: 3px; }

/* =========================================
   只读静态配置卡片流
   ========================================= */
.dp-readonly-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}
.dp-readonly-card {
  background: rgba(0,0,0,0.4);
  border: 1px solid rgba(107, 139, 158, 0.2);
  padding: 16px;
  display: flex; flex-direction: column; gap: 8px;
  transition: all 0.2s;
  border-left: 2px solid transparent;
}
.dp-readonly-card:hover { background: rgba(255,255,255,0.03); border-left-color: var(--dp-cyan-main); }
.ro-label { font-size: 12px; color: var(--dp-text-label); }
.ro-value { font-size: 15px; color: #fff; font-family: monospace; word-break: break-all; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.ro-path { font-size: 11px; color: var(--dp-text-muted); padding-top: 8px; border-top: 1px dashed rgba(255,255,255,0.1); word-break: break-all; }

/* 响应式降级 */
@media (max-width: 1024px) {
  .dp-layout-grid-2 { grid-template-columns: 1fr; }
  .dp-field-row { flex-direction: column; align-items: flex-start; gap: 12px; }
  .field-info { max-width: 100%; }
  .field-input { width: 100%; justify-content: flex-start; }
}
</style>