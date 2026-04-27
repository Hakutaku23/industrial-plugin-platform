<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { uploadPackage, type UploadPackageResult } from '../api/packages'

const selectedFile = ref<File | null>(null)
const uploading = ref(false)
const isDragging = ref(false)
const uploadProgress = ref(0)
const result = ref<UploadPackageResult | null>(null)
const error = ref('')

const assetLabel = computed(() => {
  if (!result.value) return ''
  return result.value.asset_type === 'model' ? '模型工件' : '插件包'
})

const resultNameLabel = computed(() => {
  if (!result.value) return '名称'
  return result.value.asset_type === 'model' ? '模型名称' : '插件名称'
})

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files?.length) handleFiles(input.files[0])
}

function onDrop(event: DragEvent) {
  isDragging.value = false
  const files = event.dataTransfer?.files
  if (files?.length) handleFiles(files[0])
}

function handleFiles(file: File) {
  const name = file.name.toLowerCase()
  if (name.endsWith('.zip') || name.endsWith('.tar.gz') || name.endsWith('.gz')) {
    selectedFile.value = file
    result.value = null
    error.value = ''
    uploadProgress.value = 0
  } else {
    error.value = 'FILE_TYPE_ERROR: 只支持 .zip 或 .tar.gz 格式'
  }
}

async function submit() {
  if (!selectedFile.value) return
  uploading.value = true
  error.value = ''
  result.value = null

  const timer = setInterval(() => {
    if (uploadProgress.value < 90) uploadProgress.value += (95 - uploadProgress.value) / 10
  }, 200)

  try {
    result.value = await uploadPackage(selectedFile.value)
    uploadProgress.value = 100
  } catch (err) {
    error.value = err instanceof Error ? err.message : '上传失败'
    uploadProgress.value = 0
  } finally {
    clearInterval(timer)
    setTimeout(() => { uploading.value = false }, 400)
  }
}
</script>

<template>
  <div class="cyber-container">
    <section class="panel">
      <div class="corner-tl"></div><div class="corner-tr"></div>
      <div class="corner-bl"></div><div class="corner-br"></div>

      <div class="intro">
        <div class="header-content">
          <p class="eyebrow">ARTIFACT INTAKE</p>
          <h2 class="page-title">统一上传与归档</h2>
          <p class="page-desc">
            支持插件包与模型工件包。平台根据 manifest.yaml 自动识别并归档，不在前端手工创建模型。
          </p>
        </div>
        <RouterLink class="cyber-button-outline" to="/templates">
          <svg viewBox="0 0 24 24" class="icon-sm"><path d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z" fill="none" stroke="currentColor" stroke-width="2"/></svg>
          进入模板中心
        </RouterLink>
      </div>

      <div class="manifest-rules">
        <div>
          <strong>插件包</strong>
          <span>apiVersion: plugin.platform/v1 · kind: PluginPackage</span>
        </div>
        <div>
          <strong>模型包</strong>
          <span>schema: ipp-model/v1 · model/artifacts 由 YAML 声明</span>
        </div>
      </div>

      <form class="upload-form" @submit.prevent="submit">
        <label
          class="upload-zone"
          :class="{ 'is-dragging': isDragging, 'has-file': selectedFile }"
          @dragover.prevent="isDragging = true"
          @dragleave.prevent="isDragging = false"
          @drop.prevent="onDrop"
        >
          <input type="file" accept=".zip,.gz,.tar.gz" @change="onFileChange" class="hidden-input" :disabled="uploading" />

          <div v-if="!selectedFile" class="placeholder-content">
            <div class="upload-icon-glow">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 16V4M12 4l-4 4m4-4l4 4M4 20h16"/></svg>
            </div>
            <span class="main-text">点击或将文件拖拽至此处</span>
            <span class="sub-text">PLUGIN / MODEL ARTIFACT PACKAGE · MAX_SIZE: 50MB</span>
          </div>

          <div v-else class="file-preview">
            <div class="file-card">
              <div class="file-ext">PKG</div>
              <div class="file-meta">
                <span class="name">{{ selectedFile.name }}</span>
                <span class="size">{{ (selectedFile.size / 1024).toFixed(1) }} KB</span>
              </div>
              <span v-if="!uploading" class="reselect">重新选择</span>
            </div>
          </div>

          <div class="progress-track" :class="{ 'active': uploading }">
            <div class="progress-fill" :style="{ width: uploadProgress + '%' }"></div>
          </div>
        </label>

        <div class="action-row">
          <button type="submit" class="cyber-submit-btn" :disabled="uploading || !selectedFile">
            {{ uploading ? '正在解析并归档...' : '上传并自动归档' }}
          </button>
        </div>
      </form>

      <div v-if="error" class="error-banner">
        <span class="blink">!</span> ERROR: {{ error }}
      </div>

      <div v-if="result" class="result-section">
        <div class="section-tag">归档报告 (ARTIFACT_LOG)</div>
        <div class="cyber-grid">
          <div class="grid-item">
            <label>资产类型</label>
            <span class="val highlight">{{ assetLabel }}</span>
          </div>
          <div class="grid-item">
            <label>运行状态</label>
            <span class="val status-online">{{ result.status }}</span>
          </div>
          <div class="grid-item">
            <label>{{ resultNameLabel }}</label>
            <span class="val highlight">{{ result.name }}</span>
          </div>
          <div class="grid-item">
            <label>版本号</label>
            <span class="val badge">{{ result.version }}</span>
          </div>
          <div v-if="result.asset_type === 'plugin'" class="grid-item">
            <label>插件包 ID</label>
            <span class="val code">{{ result.package_id }}</span>
          </div>
          <div v-if="result.asset_type === 'model'" class="grid-item">
            <label>模型 ID</label>
            <span class="val code">{{ result.model_id }}</span>
          </div>
          <div class="grid-item">
            <label>版本 ID</label>
            <span class="val code">{{ result.version_id }}</span>
          </div>
          <div class="grid-item full">
            <label>SHA256 摘要</label>
            <span class="val code truncate">{{ result.digest }}</span>
          </div>
        </div>
        <p v-if="result.asset_type === 'model'" class="result-hint">
          模型已根据 manifest.yaml 自动登记，可在“模型管理”中校验、上线、回滚和查看 artifacts。
        </p>
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
  background-color: var(--bg-deep);
  background-image:
    linear-gradient(rgba(0, 242, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 242, 255, 0.03) 1px, transparent 1px);
  background-size: 30px 30px;
  min-height: 100vh;
  padding: 60px 20px;
  font-family: 'Inter', 'PingFang SC', monospace;
  color: var(--text-white);
}
.panel {
  max-width: 900px;
  box-sizing: border-box;
  margin: 0 auto;
  position: relative;
  background: var(--panel-bg);
  border: 1px solid var(--border-cyan);
  padding: 40px;
  backdrop-filter: blur(15px);
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
}
[class^="corner-"] { position: absolute; width: 15px; height: 15px; border: 2px solid var(--cyan); }
.corner-tl { top: -2px; left: -2px; border-right: 0; border-bottom: 0; }
.corner-tr { top: -2px; right: -2px; border-left: 0; border-bottom: 0; }
.corner-bl { bottom: -2px; left: -2px; border-right: 0; border-top: 0; }
.corner-br { bottom: -2px; right: -2px; border-left: 0; border-top: 0; }
.intro { display: flex; justify-content: space-between; align-items: center; margin-bottom: 26px; gap: 20px; }
.eyebrow { font-size: 11px; letter-spacing: 3px; color: var(--cyan); margin: 0; }
.page-title { font-size: 28px; font-weight: 600; margin: 5px 0; color: #fff; }
.page-desc { font-size: 13px; color: var(--text-dim); margin: 0; line-height: 1.7; }
.cyber-button-outline {
  border: 1px solid var(--cyan);
  color: var(--cyan);
  padding: 8px 18px;
  font-size: 12px;
  text-decoration: none;
  display: flex;
  align-items: center;
  gap: 10px;
  background: rgba(0, 242, 255, 0.05);
  transition: 0.3s;
  white-space: nowrap;
}
.cyber-button-outline:hover { background: rgba(0, 242, 255, 0.2); box-shadow: 0 0 15px rgba(0, 242, 255, 0.2); }
.icon-sm { width: 16px; height: 16px; }
.manifest-rules {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  background: rgba(0, 242, 255, 0.22);
  border: 1px solid rgba(0, 242, 255, 0.22);
  margin-bottom: 28px;
}
.manifest-rules div { background: rgba(1, 10, 18, 0.82); padding: 14px 16px; }
.manifest-rules strong { display: block; color: #fff; font-size: 13px; margin-bottom: 6px; }
.manifest-rules span { color: rgba(160, 207, 255, 0.84); font-size: 12px; }
.upload-form { margin: 0; padding: 0; width: 100%; background: transparent; border: 0; box-shadow: none; }
.upload-zone {
  display: block;
  width: 100%;
  box-sizing: border-box;
  border: 1px dashed var(--border-cyan);
  background: linear-gradient(135deg, rgba(0, 242, 255, 0.035), rgba(0, 0, 0, 0.45));
  padding: 56px 40px;
  text-align: center;
  cursor: pointer;
  position: relative;
  overflow: hidden;
  transition: border-color 0.25s ease, background 0.25s ease, box-shadow 0.25s ease;
}
.upload-zone::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: linear-gradient(90deg, transparent 0, rgba(0, 242, 255, 0.08) 50%, transparent 100%);
  opacity: 0.25;
}
.upload-zone.is-dragging { background: rgba(0, 242, 255, 0.1); border-color: var(--border-cyan-strong); box-shadow: 0 0 22px rgba(0, 242, 255, 0.16) inset; }
.upload-zone.has-file { border-style: solid; border-color: var(--border-cyan-strong); background: linear-gradient(135deg, rgba(0, 242, 255, 0.09), rgba(2, 15, 26, 0.86)); }
.upload-icon-glow svg { width: 48px; height: 48px; color: var(--cyan); filter: drop-shadow(0 0 10px var(--cyan)); margin-bottom: 20px; }
.main-text { display: block; font-size: 16px; color: #fff; margin-bottom: 10px; }
.sub-text { font-size: 12px; color: var(--text-dim); font-family: monospace; }
.file-preview { position: relative; z-index: 1; width: 100%; }
.file-card { display: flex; align-items: center; gap: 18px; width: 100%; max-width: 100%; box-sizing: border-box; text-align: left; color: var(--text-white); }
.file-ext { flex: 0 0 auto; min-width: 44px; height: 44px; display: inline-flex; align-items: center; justify-content: center; background: rgba(0, 242, 255, 0.16); color: var(--cyan); border: 1px solid var(--border-cyan-strong); box-shadow: 0 0 16px rgba(0, 242, 255, 0.12); font-weight: 800; padding: 0 10px; font-size: 12px; border-radius: 2px; letter-spacing: 1px; }
.file-meta { min-width: 0; flex: 1 1 auto; }
.file-meta .name { display: block; max-width: 100%; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; font-size: 16px; color: var(--text-white); }
.file-meta .size { font-size: 12px; color: var(--text-dim); }
.reselect { flex: 0 0 auto; margin-left: 12px; font-size: 12px; color: var(--cyan); text-decoration: underline; }
.progress-track { position: absolute; bottom: 0; left: 0; width: 100%; height: 3px; background: rgba(255, 255, 255, 0.1); display: none; }
.progress-track.active { display: block; }
.progress-fill { height: 100%; background: var(--cyan); box-shadow: 0 0 15px var(--cyan); transition: width 0.3s; }
.action-row { margin-top: 30px; display: flex; justify-content: flex-end; }
.cyber-submit-btn { background: var(--cyan); color: #000; border: none; padding: 14px 50px; font-weight: 800; cursor: pointer; clip-path: polygon(15px 0, 100% 0, calc(100% - 15px) 100%, 0 100%); transition: 0.3s; }
.cyber-submit-btn:disabled { background: #1a2a35; color: #444; clip-path: none; cursor: not-allowed; }
.cyber-submit-btn:hover:not(:disabled) { filter: brightness(1.2); box-shadow: 0 0 30px rgba(0, 242, 255, 0.4); }
.result-section { margin-top: 50px; border-top: 1px solid var(--border-cyan); padding-top: 30px; }
.section-tag { font-size: 12px; color: var(--cyan); margin-bottom: 20px; letter-spacing: 2px; }
.cyber-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1px; background: var(--border-cyan); border: 1px solid var(--border-cyan); }
.grid-item { background: rgba(1, 10, 18, 0.9); padding: 20px; display: flex; flex-direction: column; gap: 8px; }
.grid-item.full { grid-column: span 2; }
.grid-item label { font-size: 11px; color: var(--text-dim); text-transform: uppercase; }
.grid-item .val { font-size: 14px; color: #fff; }
.grid-item .val.code { font-family: 'Courier New', monospace; color: var(--cyan); opacity: 0.8; }
.grid-item .val.status-online { color: #00ffcc; font-weight: bold; }
.grid-item .val.status-online::before { content: '●'; margin-right: 8px; }
.grid-item .val.badge { background: rgba(0, 242, 255, 0.1); border: 1px solid var(--cyan); padding: 2px 8px; font-size: 12px; width: fit-content; }
.result-hint { margin: 18px 0 0; color: rgba(160, 207, 255, 0.86); font-size: 13px; }
.error-banner { margin-top: 25px; color: #ff4d4d; border: 1px solid rgba(255, 77, 77, 0.3); padding: 12px; background: rgba(255, 77, 77, 0.05); font-family: monospace; font-size: 13px; }
.blink { animation: blink 1s infinite; font-weight: bold; margin-right: 10px; }
@keyframes blink { 50% { opacity: 0; } }
.truncate { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.hidden-input { display: none; }
@media (max-width: 768px) {
  .cyber-container { padding: 32px 14px; }
  .panel { padding: 26px 18px; }
  .intro { flex-direction: column; align-items: flex-start; gap: 18px; }
  .manifest-rules { grid-template-columns: 1fr; }
  .upload-zone { padding: 38px 20px; }
  .file-card { gap: 12px; }
  .reselect { margin-left: 0; }
  .action-row { justify-content: stretch; }
  .cyber-submit-btn { width: 100%; }
  .cyber-grid { grid-template-columns: 1fr; }
  .grid-item.full { grid-column: span 1; }
}
</style>
