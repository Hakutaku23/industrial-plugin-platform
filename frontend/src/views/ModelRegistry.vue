<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  listModels,
  listModelVersions,
  promoteModelVersion,
  rollbackModel,
  validateModelVersion,
  type ModelSummary,
  type ModelVersionRecord,
} from '../api/models'

const models = ref<ModelSummary[]>([])
const versions = ref<ModelVersionRecord[]>([])
const selectedModelId = ref<number | null>(null)
const loading = ref(false)
const operating = ref(false)
const error = ref('')
const notice = ref('')

const selectedModel = computed(() => models.value.find((item) => item.id === selectedModelId.value) ?? null)

async function loadModels() {
  loading.value = true
  error.value = ''
  try {
    models.value = await listModels()
    if (!selectedModelId.value && models.value.length > 0) {
      selectedModelId.value = models.value[0].id
    }
    if (selectedModelId.value) {
      await loadVersions(selectedModelId.value)
    } else {
      versions.value = []
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '模型列表加载失败'
  } finally {
    loading.value = false
  }
}

async function loadVersions(modelId: number) {
  versions.value = await listModelVersions(modelId)
}

async function selectModel(model: ModelSummary) {
  selectedModelId.value = model.id
  error.value = ''
  notice.value = ''
  try {
    await loadVersions(model.id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '模型版本加载失败'
  }
}

async function validateVersion(version: ModelVersionRecord) {
  operating.value = true
  error.value = ''
  notice.value = ''
  try {
    await validateModelVersion(version.model_id, version.id)
    notice.value = '模型版本校验通过'
    await loadModels()
    await loadVersions(version.model_id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '模型版本校验失败'
  } finally {
    operating.value = false
  }
}

async function promoteVersion(version: ModelVersionRecord) {
  operating.value = true
  error.value = ''
  notice.value = ''
  try {
    await promoteModelVersion(version.model_id, version.id)
    notice.value = 'active 模型版本已切换'
    await loadModels()
    await loadVersions(version.model_id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '模型版本上线失败'
  } finally {
    operating.value = false
  }
}

async function rollbackSelectedModel() {
  if (!selectedModel.value) return
  operating.value = true
  error.value = ''
  notice.value = ''
  try {
    await rollbackModel(selectedModel.value.id)
    notice.value = '模型已回滚到上一版本'
    await loadModels()
    await loadVersions(selectedModel.value.id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '模型回滚失败'
  } finally {
    operating.value = false
  }
}

function artifactKeys(version: ModelVersionRecord) {
  return Object.keys(version.artifacts || {}).join(', ') || '-'
}

function metricText(version: ModelVersionRecord, key: string) {
  const metrics = version.metrics?.metrics
  if (!metrics || typeof metrics !== 'object') return 'N/A'
  const value = (metrics as Record<string, unknown>)[key]
  return value === null || value === undefined || value === '' ? 'N/A' : String(value)
}

function schemaName(version: ModelVersionRecord) {
  return String(version.manifest?.schema || '-')
}

onMounted(loadModels)
</script>

<template>
  <section class="model-page">
    <div class="model-header">
      <div>
        <p class="eyebrow">MODEL REGISTRY</p>
        <h2>模型工件管理</h2>
        <p class="subline">模型只来自用户上传的模型包，名称、版本、family_fingerprint 与 artifacts 均由 manifest.yaml 解析。</p>
      </div>
      <div class="header-actions">
        <RouterLink class="primary-btn" to="/packages/upload">上传模型包</RouterLink>
        <button class="ghost-btn" type="button" :disabled="loading" @click="loadModels">刷新</button>
      </div>
    </div>

    <p v-if="error" class="message error">{{ error }}</p>
    <p v-if="notice" class="message ok">{{ notice }}</p>

    <div class="model-grid">
      <aside class="panel model-list-panel">
        <div class="panel-title">
          <h3>模型列表</h3>
          <span>{{ models.length }} 项</span>
        </div>
        <p class="panel-hint">没有“创建模型”入口。上传包解析成功后，平台自动登记或追加版本。</p>

        <div class="model-list">
          <button
            v-for="item in models"
            :key="item.id"
            type="button"
            class="model-item"
            :class="{ active: selectedModelId === item.id }"
            @click="selectModel(item)"
          >
            <strong>{{ item.display_name }}</strong>
            <span>{{ item.model_name }}</span>
            <em>{{ item.active_version || '未上线' }}</em>
          </button>
          <div v-if="!models.length && !loading" class="empty">
            暂无模型。请到“统一上传与归档”上传 ipp-model/v1 模型包。
          </div>
        </div>
      </aside>

      <main class="panel detail-panel">
        <template v-if="selectedModel">
          <div class="detail-head">
            <div>
              <h3>{{ selectedModel.display_name }}</h3>
              <p>{{ selectedModel.model_name }} · {{ selectedModel.status }}</p>
              <p class="fingerprint">{{ selectedModel.family_fingerprint }}</p>
              <p v-if="selectedModel.description" class="description">{{ selectedModel.description }}</p>
            </div>
            <button class="danger-btn" type="button" :disabled="operating || !selectedModel.active_version_id" @click="rollbackSelectedModel">
              回滚
            </button>
          </div>

          <div class="summary-grid">
            <div>
              <label>ACTIVE VERSION</label>
              <strong>{{ selectedModel.active_version || '未上线' }}</strong>
            </div>
            <div>
              <label>OWNER</label>
              <strong>{{ selectedModel.owner }}</strong>
            </div>
            <div>
              <label>UPDATED</label>
              <strong>{{ selectedModel.updated_at }}</strong>
            </div>
          </div>

          <table class="version-table">
            <thead>
              <tr>
                <th>版本</th>
                <th>状态</th>
                <th>Schema</th>
                <th>Artifacts</th>
                <th>指标</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="version in versions" :key="version.id">
                <td>{{ version.version }}</td>
                <td>
                  <span class="status-pill" :class="version.status.toLowerCase()">{{ version.status }}</span>
                </td>
                <td>{{ schemaName(version) }}</td>
                <td class="artifact-cell">{{ artifactKeys(version) }}</td>
                <td class="metric-cell">R² {{ metricText(version, 'r2') }} / MAE {{ metricText(version, 'mae') }}</td>
                <td>{{ version.created_at }}</td>
                <td class="actions">
                  <button type="button" class="ghost-btn" :disabled="operating" @click="validateVersion(version)">校验</button>
                  <button type="button" class="primary-btn" :disabled="operating" @click="promoteVersion(version)">上线</button>
                </td>
              </tr>
              <tr v-if="!versions.length">
                <td colspan="7" class="empty">暂无模型版本</td>
              </tr>
            </tbody>
          </table>
        </template>

        <template v-else>
          <div class="empty big">
            <p>暂无模型工件</p>
            <RouterLink class="primary-btn" to="/packages/upload">上传模型包</RouterLink>
          </div>
        </template>
      </main>
    </div>
  </section>
</template>

<style scoped>
.model-page {
  color: #d9f7ff;
  padding: 10px 0 40px;
}

.model-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 20px;
  padding: 20px 24px;
  border: 1px solid rgba(0, 243, 255, 0.28);
  background: rgba(2, 18, 38, 0.72);
  box-shadow: inset 0 0 22px rgba(0, 243, 255, 0.08);
}

.eyebrow {
  margin: 0 0 6px;
  color: #00f3ff;
  font-size: 11px;
  letter-spacing: 0.28em;
}

h2, h3 {
  margin: 0;
  color: #ffffff;
}

.subline, .panel-hint, .description {
  margin: 8px 0 0;
  color: rgba(160, 207, 255, 0.76);
  font-size: 13px;
  line-height: 1.7;
}

.header-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.model-grid {
  display: grid;
  grid-template-columns: 330px minmax(0, 1fr);
  gap: 18px;
}

.panel {
  border: 1px solid rgba(0, 243, 255, 0.24);
  background: rgba(3, 13, 28, 0.82);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.28);
  padding: 18px;
}

.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.panel-title span {
  color: #00f3ff;
  font-size: 12px;
}

.model-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 14px;
}

.model-item {
  text-align: left;
  border: 1px solid rgba(0, 243, 255, 0.18);
  background: rgba(0, 243, 255, 0.04);
  color: #d9f7ff;
  padding: 12px;
  cursor: pointer;
  transition: 0.2s;
}

.model-item:hover,
.model-item.active {
  border-color: #00f3ff;
  background: rgba(0, 243, 255, 0.13);
}

.model-item strong,
.model-item span,
.model-item em {
  display: block;
}

.model-item strong {
  color: #ffffff;
  font-size: 14px;
}

.model-item span {
  margin-top: 4px;
  color: rgba(160, 207, 255, 0.8);
  font-size: 12px;
}

.model-item em {
  margin-top: 8px;
  color: #00f3ff;
  font-style: normal;
  font-size: 12px;
}

.detail-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(0, 243, 255, 0.18);
}

.detail-head p {
  margin: 6px 0 0;
  color: rgba(160, 207, 255, 0.8);
}

.fingerprint {
  font-family: "Courier New", monospace;
  color: #00f3ff !important;
  word-break: break-all;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1px;
  background: rgba(0, 243, 255, 0.18);
  border: 1px solid rgba(0, 243, 255, 0.18);
  margin: 16px 0;
}

.summary-grid div {
  background: rgba(1, 10, 18, 0.9);
  padding: 14px;
}

.summary-grid label {
  display: block;
  color: rgba(160, 207, 255, 0.64);
  font-size: 11px;
  margin-bottom: 7px;
}

.summary-grid strong {
  color: #ffffff;
  font-size: 13px;
  word-break: break-all;
}

.version-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.version-table th,
.version-table td {
  border-bottom: 1px solid rgba(0, 243, 255, 0.12);
  padding: 11px 10px;
  text-align: left;
  vertical-align: top;
}

.version-table th {
  color: #00f3ff;
  font-size: 12px;
  font-weight: 700;
}

.artifact-cell,
.metric-cell {
  max-width: 260px;
  color: rgba(160, 207, 255, 0.82);
  word-break: break-word;
}

.status-pill {
  display: inline-flex;
  border: 1px solid rgba(0, 243, 255, 0.38);
  color: #00f3ff;
  padding: 2px 8px;
  font-size: 11px;
}

.status-pill.active {
  color: #00ffcc;
  border-color: rgba(0, 255, 204, 0.5);
}

.status-pill.archived {
  color: rgba(160, 207, 255, 0.72);
  border-color: rgba(160, 207, 255, 0.24);
}

.actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.primary-btn,
.ghost-btn,
.danger-btn {
  border: 1px solid #00f3ff;
  color: #00f3ff;
  background: rgba(0, 243, 255, 0.08);
  padding: 7px 12px;
  cursor: pointer;
  text-decoration: none;
  font-size: 12px;
  white-space: nowrap;
}

.primary-btn {
  background: #00f3ff;
  color: #04121f;
  font-weight: 800;
}

.danger-btn {
  border-color: #ff4d4d;
  color: #ff4d4d;
  background: rgba(255, 77, 77, 0.08);
}

button:disabled,
a[aria-disabled="true"] {
  opacity: 0.45;
  cursor: not-allowed;
}

.message {
  border: 1px solid;
  padding: 10px 12px;
  margin: 0 0 14px;
  font-size: 13px;
}

.message.error {
  color: #ff6666;
  border-color: rgba(255, 102, 102, 0.35);
  background: rgba(255, 102, 102, 0.08);
}

.message.ok {
  color: #00ffcc;
  border-color: rgba(0, 255, 204, 0.35);
  background: rgba(0, 255, 204, 0.08);
}

.empty {
  color: rgba(160, 207, 255, 0.68);
  padding: 20px;
  text-align: center;
}

.empty.big {
  min-height: 360px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 16px;
}

@media (max-width: 1080px) {
  .model-grid {
    grid-template-columns: 1fr;
  }

  .summary-grid {
    grid-template-columns: 1fr;
  }
}
</style>
