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
  <div class="settings-page">
    <section class="panel">
      <div class="header-row">
        <div>
          <p class="eyebrow">SYSTEM SETTINGS</p>
          <h2>系统设置</h2>
          <p class="desc">集中管理维护类运行时配置。安全、许可证、数据库连接等高风险配置仅展示，不支持前端热修改。</p>
        </div>
        <div class="actions">
          <button type="button" class="btn ghost" :disabled="loading" @click="loadAll">刷新</button>
          <button type="button" class="btn primary" :disabled="saving || loading" @click="saveSettings">保存设置</button>
        </div>
      </div>

      <div v-if="error" class="error">{{ error }}</div>
      <div v-if="message" class="success">{{ message }}</div>

      <div class="meta-box">
        <span>设置文件</span>
        <code>{{ settingsFile }}</code>
      </div>

      <div class="grid-two">
        <article class="card">
          <div class="card-head">
            <h3>runs 目录清理</h3>
            <span>var/runs/run-*</span>
          </div>
          <div class="form-list">
            <label v-for="item in runDirItems" :key="item.path" class="field">
              <div class="field-label">
                <strong>{{ item.label }}</strong>
                <small>{{ item.description }}</small>
              </div>
              <input
                v-if="item.type === 'bool'"
                type="checkbox"
                :checked="Boolean(inputValue(item.path))"
                @change="updateValue(item, $event)"
              />
              <input
                v-else
                :type="item.type === 'str' ? 'text' : 'number'"
                :min="item.minimum ?? undefined"
                :max="item.maximum ?? undefined"
                :value="inputValue(item.path)"
                @input="updateValue(item, $event)"
              />
            </label>
          </div>
          <div class="button-row">
            <button class="btn ghost" :disabled="saving" @click="runCleanup('runs', true)">演练清理</button>
            <button class="btn danger" :disabled="saving" @click="runCleanup('runs', false)">立即清理</button>
          </div>
          <pre class="report">{{ JSON.stringify(status?.run_directory_cleanup || {}, null, 2) }}</pre>
        </article>

        <article class="card">
          <div class="card-head">
            <h3>数据库历史记录清理</h3>
            <span>plugin_runs / run_logs / writeback_records / audit_events</span>
          </div>
          <div class="form-list">
            <label v-for="item in dbItems" :key="item.path" class="field">
              <div class="field-label">
                <strong>{{ item.label }}</strong>
                <small>{{ item.description }}</small>
              </div>
              <input
                v-if="item.type === 'bool'"
                type="checkbox"
                :checked="Boolean(inputValue(item.path))"
                @change="updateValue(item, $event)"
              />
              <input
                v-else
                :type="item.type === 'str' ? 'text' : 'number'"
                :min="item.minimum ?? undefined"
                :max="item.maximum ?? undefined"
                :value="inputValue(item.path)"
                @input="updateValue(item, $event)"
              />
            </label>
          </div>
          <div class="button-row">
            <button class="btn ghost" :disabled="saving" @click="runCleanup('db', true)">演练清理</button>
            <button class="btn danger" :disabled="saving" @click="runCleanup('db', false)">立即清理</button>
          </div>
          <pre class="report">{{ JSON.stringify(status?.database_cleanup || {}, null, 2) }}</pre>
        </article>
      </div>

      <article class="card readonly-card">
        <div class="card-head">
          <h3>静态系统配置扫描</h3>
          <span>只读展示；这些配置建议通过环境变量或 config/platform.yaml 管理</span>
        </div>
        <div class="readonly-grid">
          <div v-for="item in runtimeReadonly" :key="item.path" class="readonly-item">
            <span>{{ item.label }}</span>
            <strong>{{ formatValue(item.value) }}</strong>
            <small>{{ item.path }}</small>
          </div>
        </div>
      </article>
    </section>
  </div>
</template>

<style scoped>
.settings-page {
  min-height: 100vh;
  padding: 34px;
  color: #d9f7ff;
  background:
    linear-gradient(rgba(0, 243, 255, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 243, 255, 0.035) 1px, transparent 1px),
    #030a16;
  background-size: 32px 32px;
}
.panel {
  max-width: 1480px;
  margin: 0 auto;
  padding: 30px;
  background: rgba(2, 18, 38, 0.78);
  border: 1px solid rgba(0, 243, 255, 0.28);
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.4);
}
.header-row, .card-head, .button-row {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: center;
}
.eyebrow { color: #00f3ff; letter-spacing: 3px; font-size: 11px; margin: 0 0 8px; }
h2 { margin: 0 0 8px; color: #fff; }
.desc { margin: 0; color: rgba(217, 247, 255, 0.65); font-size: 13px; }
.actions, .button-row { display: flex; gap: 12px; }
.btn {
  border: 1px solid rgba(0, 243, 255, 0.45);
  background: rgba(0, 243, 255, 0.06);
  color: #00f3ff;
  padding: 9px 16px;
  cursor: pointer;
  font-weight: 800;
}
.btn.primary { background: #00f3ff; color: #001018; }
.btn.danger { border-color: rgba(255, 83, 112, 0.7); color: #ff7890; background: rgba(255, 83, 112, 0.08); }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.error, .success, .meta-box { margin-top: 18px; padding: 12px 14px; border: 1px solid; }
.error { color: #ff7890; border-color: rgba(255, 83, 112, 0.45); background: rgba(255, 83, 112, 0.08); }
.success { color: #00ffcc; border-color: rgba(0, 255, 204, 0.45); background: rgba(0, 255, 204, 0.08); }
.meta-box { display: flex; gap: 12px; align-items: center; border-color: rgba(0, 243, 255, 0.2); color: rgba(217,247,255,.72); }
code { color: #00f3ff; overflow-wrap: anywhere; }
.grid-two { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; margin-top: 22px; }
.card {
  padding: 20px;
  background: rgba(1, 10, 18, 0.72);
  border: 1px solid rgba(0, 243, 255, 0.22);
}
.card h3 { margin: 0; color: #fff; }
.card-head span { color: rgba(217, 247, 255, 0.55); font-size: 12px; text-align: right; }
.form-list { display: grid; gap: 12px; margin: 18px 0; }
.field {
  display: grid;
  grid-template-columns: 1fr 180px;
  gap: 16px;
  align-items: center;
  padding: 12px;
  background: rgba(0, 243, 255, 0.035);
  border: 1px solid rgba(0, 243, 255, 0.12);
}
.field-label { display: grid; gap: 4px; }
.field-label small { color: rgba(217, 247, 255, 0.55); }
input[type='number'], input[type='text'] {
  width: 100%;
  box-sizing: border-box;
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(0, 243, 255, 0.32);
  color: #d9f7ff;
  padding: 8px 10px;
}
input[type='checkbox'] { width: 22px; height: 22px; justify-self: end; accent-color: #00f3ff; }
.report {
  min-height: 110px;
  max-height: 220px;
  overflow: auto;
  margin: 16px 0 0;
  padding: 12px;
  color: #98f7ff;
  background: rgba(0, 0, 0, 0.32);
  border: 1px solid rgba(0, 243, 255, 0.16);
  font-size: 12px;
}
.readonly-card { margin-top: 20px; }
.readonly-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 18px; }
.readonly-item { display: grid; gap: 5px; padding: 12px; background: rgba(255,255,255,.035); border: 1px solid rgba(255,255,255,.08); }
.readonly-item span { color: rgba(217,247,255,.72); }
.readonly-item strong { color: #fff; overflow-wrap: anywhere; }
.readonly-item small { color: rgba(217,247,255,.38); overflow-wrap: anywhere; }
@media (max-width: 1100px) {
  .grid-two, .readonly-grid { grid-template-columns: 1fr; }
  .header-row, .card-head { align-items: flex-start; flex-direction: column; }
  .field { grid-template-columns: 1fr; }
  input[type='checkbox'] { justify-self: start; }
}
</style>
