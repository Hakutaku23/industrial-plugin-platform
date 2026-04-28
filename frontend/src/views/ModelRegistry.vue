<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  checkModelDelete,
  deleteModel,
  listModels,
  listModelVersions,
  promoteModelVersion,
  rollbackModel,
  validateModelVersion,
  type ModelDeleteCheck,
  type ModelSummary,
  type ModelVersionRecord,
} from '../api/models'

const models = ref<ModelSummary[]>([])
const versions = ref<ModelVersionRecord[]>([])
const selectedModelId = ref<number | null>(null)
const loading = ref(false)
const operating = ref(false)
const deleting = ref(false)
const error = ref('')
const notice = ref('')
const deletePreview = ref<ModelDeleteCheck | null>(null)

const selectedModel = computed(() => models.value.find((item) => item.id === selectedModelId.value) ?? null)

async function loadModels() {
  loading.value = true
  error.value = ''
  try {
    models.value = await listModels()
    if (selectedModelId.value && !models.value.some((item) => item.id === selectedModelId.value)) {
      selectedModelId.value = models.value[0]?.id ?? null
    }
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
  deletePreview.value = null
}

async function selectModel(model: ModelSummary) {
  selectedModelId.value = model.id
  error.value = ''
  notice.value = ''
  deletePreview.value = null
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

async function previewDeleteSelectedModel() {
  if (!selectedModel.value) return
  deleting.value = true
  error.value = ''
  notice.value = ''
  try {
    deletePreview.value = await checkModelDelete(selectedModel.value.id)
    if (deletePreview.value.blockers.length > 0) {
      error.value = `模型暂不能删除：${deletePreview.value.blockers.map((item) => item.message).join('；')}`
      return
    }
    if (deletePreview.value.requires_force) {
      notice.value = '该模型存在 active 版本。如确认没有实例或模型更新任务引用，可再次点击删除并确认强制删除。'
      return
    }
    await confirmDeleteSelectedModel(false)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '模型删除检查失败'
  } finally {
    deleting.value = false
  }
}

async function confirmDeleteSelectedModel(force: boolean) {
  if (!selectedModel.value) return
  const model = selectedModel.value
  const message = force
    ? `确认强制删除模型 ${model.model_name} 及其磁盘文件？该操作不可恢复。`
    : `确认删除模型 ${model.model_name} 及其磁盘文件？该操作不可恢复。`
  if (!window.confirm(message)) return

  deleting.value = true
  error.value = ''
  notice.value = ''
  try {
    await deleteModel({
      modelId: model.id,
      force,
      delete_files: true,
      reason: force ? 'force delete unused active model from UI' : 'delete unused model from UI',
    })
    notice.value = `模型 ${model.model_name} 已删除，磁盘模型目录已清理。`
    selectedModelId.value = null
    versions.value = []
    deletePreview.value = null
    await loadModels()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '模型删除失败'
  } finally {
    deleting.value = false
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

function formatBytes(value: number) {
  if (!Number.isFinite(value) || value <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = value
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`
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
            <div class="detail-actions">
              <button class="danger-btn" type="button" :disabled="operating || !selectedModel.active_version_id" @click="rollbackSelectedModel">
                回滚
              </button>
              <button class="danger-btn" type="button" :disabled="deleting || operating" @click="previewDeleteSelectedModel">
                删除模型
              </button>
              <button
                v-if="deletePreview?.requires_force && deletePreview.can_delete_with_force && !deletePreview.blockers.length"
                class="danger-solid-btn"
                type="button"
                :disabled="deleting || operating"
                @click="confirmDeleteSelectedModel(true)"
              >
                强制删除
              </button>
            </div>
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

          <div v-if="deletePreview" class="delete-panel">
            <div class="delete-title">
              <strong>删除检查</strong>
              <span>{{ deletePreview.deletable ? '可删除' : deletePreview.can_delete_with_force ? '需确认' : '被引用' }}</span>
            </div>
            <div class="delete-grid">
              <div>
                <label>模型目录</label>
                <p>{{ deletePreview.storage.model_dir }}</p>
              </div>
              <div>
                <label>文件数量</label>
                <p>{{ deletePreview.storage.file_count }}</p>
              </div>
              <div>
                <label>占用空间</label>
                <p>{{ formatBytes(deletePreview.storage.total_bytes) }}</p>
              </div>
            </div>
            <p v-for="item in deletePreview.blockers" :key="item.code" class="delete-warning blocked">{{ item.message }}</p>
            <p v-for="item in deletePreview.warnings" :key="item.code" class="delete-warning">{{ item.message }}</p>
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
  max-width: 1600px;
  margin: 0 auto;
  color: #d9f7ff;
  padding: 16px 24px 40px;
  box-sizing: border-box;
}

.model-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 16px;
  padding: 16px 20px;
  border: 1px solid rgba(0, 243, 255, 0.28);
  background: rgba(2, 18, 38, 0.72);
  box-shadow: inset 0 0 22px rgba(0, 243, 255, 0.08);
  border-radius: 6px;
}

.eyebrow { margin: 0 0 4px; color: #00f3ff; font-size: 11px; letter-spacing: 0.2em; }
h2 { margin: 0; color: #ffffff; font-size: 20px; }
h3 { margin: 0; color: #ffffff; font-size: 16px; }
.subline, .panel-hint, .description { margin: 6px 0 0; color: rgba(160, 207, 255, 0.76); font-size: 12px; line-height: 1.5; }
.header-actions { display: flex; gap: 12px; flex-wrap: wrap; }
.model-grid { display: grid !important; grid-template-columns: 280px minmax(0, 1fr) !important; gap: 20px !important; align-items: start; width: 100% !important; margin: 0 !important; }
.panel { border: 1px solid rgba(0, 243, 255, 0.24); background: rgba(3, 13, 28, 0.82); box-shadow: 0 8px 24px rgba(0, 0, 0, 0.28); padding: 16px; border-radius: 6px; box-sizing: border-box !important; }
.model-list-panel, .detail-panel { width: 100% !important; max-width: none !important; margin: 0 !important; }
.panel-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; padding-bottom: 8px; border-bottom: 1px dashed rgba(0, 243, 255, 0.15); }
.panel-title span { color: #00f3ff; font-size: 12px; background: rgba(0, 243, 255, 0.1); padding: 2px 6px; border-radius: 10px; }
.model-list { display: flex; flex-direction: column; gap: 8px; margin-top: 10px; }
.model-item { text-align: left; border: 1px solid rgba(0, 243, 255, 0.12); background: rgba(0, 243, 255, 0.02); color: #d9f7ff; padding: 10px 12px; cursor: pointer; transition: all 0.2s ease-in-out; border-radius: 4px; }
.model-item:hover { border-color: rgba(0, 243, 255, 0.5); background: rgba(0, 243, 255, 0.08); }
.model-item.active { border-color: #00f3ff; background: rgba(0, 243, 255, 0.15); box-shadow: inset 2px 0 0 #00f3ff; }
.model-item strong { display: block; color: #ffffff; font-size: 13px; margin-bottom: 2px; }
.model-item span { display: block; color: rgba(160, 207, 255, 0.6); font-size: 11px; }
.model-item em { display: inline-block; margin-top: 6px; padding: 2px 6px; background: rgba(0, 243, 255, 0.1); border-radius: 2px; color: #00f3ff; font-style: normal; font-size: 11px; }
.detail-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; padding-bottom: 12px; margin-bottom: 12px; border-bottom: 1px solid rgba(0, 243, 255, 0.15); }
.detail-head p { margin: 4px 0 0; color: rgba(160, 207, 255, 0.8); font-size: 13px; }
.detail-actions { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.fingerprint { font-family: "Courier New", monospace; color: #00f3ff !important; word-break: break-all; font-size: 12px !important; opacity: 0.8; }
.summary-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1px; background: rgba(0, 243, 255, 0.18); border: 1px solid rgba(0, 243, 255, 0.18); margin: 12px 0 16px; border-radius: 4px; overflow: hidden; }
.summary-grid div { background: rgba(1, 10, 18, 0.95); padding: 10px 14px; }
.summary-grid label { display: block; color: rgba(160, 207, 255, 0.5); font-size: 11px; margin-bottom: 4px; }
.summary-grid strong { color: #ffffff; font-size: 13px; word-break: break-all; }
.delete-panel { border: 1px solid rgba(255, 180, 0, 0.28); background: rgba(255, 180, 0, 0.05); padding: 12px; margin: 0 0 16px; border-radius: 4px; }
.delete-title { display: flex; justify-content: space-between; align-items: center; color: #ffd166; font-size: 13px; margin-bottom: 8px; }
.delete-title span { border: 1px solid rgba(255, 209, 102, 0.4); padding: 2px 6px; border-radius: 2px; }
.delete-grid { display: grid; grid-template-columns: minmax(0, 1fr) 120px 120px; gap: 1px; background: rgba(255, 209, 102, 0.18); margin-bottom: 8px; }
.delete-grid div { background: rgba(1, 10, 18, 0.95); padding: 8px; min-width: 0; }
.delete-grid label { display: block; color: rgba(255, 209, 102, 0.62); font-size: 11px; }
.delete-grid p { margin: 4px 0 0; color: #fff; font-size: 12px; word-break: break-all; }
.delete-warning { margin: 6px 0 0; color: #ffd166; font-size: 12px; }
.delete-warning.blocked { color: #ff6666; }
.version-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.version-table th, .version-table td { border-bottom: 1px solid rgba(0, 243, 255, 0.1); padding: 10px 8px; text-align: left; vertical-align: middle; }
.version-table th { color: #00f3ff; font-size: 12px; font-weight: normal; background: rgba(0, 243, 255, 0.03); }
.version-table tbody tr { transition: background 0.2s; }
.version-table tbody tr:hover { background: rgba(0, 243, 255, 0.05); }
.artifact-cell, .metric-cell { max-width: 220px; color: rgba(160, 207, 255, 0.82); word-break: break-word; line-height: 1.4; }
.status-pill { display: inline-flex; border: 1px solid rgba(0, 243, 255, 0.38); color: #00f3ff; padding: 2px 6px; font-size: 11px; border-radius: 2px; }
.status-pill.active { color: #00ffcc; border-color: rgba(0, 255, 204, 0.5); background: rgba(0, 255, 204, 0.05); }
.status-pill.archived, .status-pill.rejected { color: rgba(160, 207, 255, 0.5); border-color: rgba(160, 207, 255, 0.2); }
.actions { display: flex; gap: 6px; flex-wrap: wrap; }
.primary-btn, .ghost-btn, .danger-btn, .danger-solid-btn { border: 1px solid #00f3ff; color: #00f3ff; background: rgba(0, 243, 255, 0.05); padding: 5px 12px; border-radius: 3px; cursor: pointer; text-decoration: none; font-size: 12px; white-space: nowrap; transition: all 0.2s ease; display: inline-flex; align-items: center; justify-content: center; }
.primary-btn { background: #00f3ff; color: #04121f; font-weight: 600; }
.primary-btn:hover:not(:disabled) { background: #33f6ff; box-shadow: 0 0 10px rgba(0, 243, 255, 0.4); }
.ghost-btn:hover:not(:disabled) { background: rgba(0, 243, 255, 0.15); }
.danger-btn { border-color: #ff4d4d; color: #ff4d4d; background: rgba(255, 77, 77, 0.05); }
.danger-btn:hover:not(:disabled) { background: rgba(255, 77, 77, 0.15); }
.danger-solid-btn { border-color: #ff4d4d; color: #fff; background: rgba(255, 77, 77, 0.75); }
.danger-solid-btn:hover:not(:disabled) { box-shadow: 0 0 12px rgba(255, 77, 77, 0.45); }
button:disabled, a[aria-disabled="true"] { opacity: 0.3; cursor: not-allowed; filter: grayscale(1); }
.message { border: 1px solid; padding: 8px 12px; margin: 0 0 16px; font-size: 12px; border-radius: 4px; display: flex; align-items: center; }
.message.error { color: #ff6666; border-color: rgba(255, 102, 102, 0.35); background: rgba(255, 102, 102, 0.08); }
.message.ok { color: #00ffcc; border-color: rgba(0, 255, 204, 0.35); background: rgba(0, 255, 204, 0.08); }
.empty { color: rgba(160, 207, 255, 0.4); padding: 30px 20px; text-align: center; font-size: 12px; }
.empty.big { min-height: 300px; display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 16px; }
@media (max-width: 1080px) { .model-grid { grid-template-columns: 1fr !important; } .summary-grid, .delete-grid { grid-template-columns: 1fr; } }
</style>
