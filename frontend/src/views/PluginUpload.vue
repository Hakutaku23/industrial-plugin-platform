<script setup lang="ts">
import { ref } from 'vue'
import { uploadPackage, type UploadPackageResult } from '../api/packages'

const selectedFile = ref<File | null>(null)
const uploading = ref(false)
const uploadProgress = ref(0) // 新增：进度条状态
const result = ref<UploadPackageResult | null>(null)
const error = ref('')

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] ?? null
  result.value = null
  error.value = ''
  uploadProgress.value = 0 // 重新选择文件时重置进度
}

async function submit() {
  if (!selectedFile.value) {
    error.value = '请选择 zip 或 tar.gz 插件包'
    return
  }

  uploading.value = true
  error.value = ''
  result.value = null
  uploadProgress.value = 0

  // 💡 体验优化：平滑模拟进度条
  // 因为底层的 Promise 无法直接抛出进度，这里用定时器模拟平滑上传到 90%
  // 如果未来您的 uploadPackage API 支持 onUploadProgress，可直接替换此处逻辑
  const timer = setInterval(() => {
    if (uploadProgress.value < 90) {
      const increment = Math.max(1, (95 - uploadProgress.value) / 10)
      uploadProgress.value += increment
    }
  }, 200)

  try {
    result.value = await uploadPackage(selectedFile.value)
    uploadProgress.value = 100 // 成功后瞬间拉满
  } catch (err) {
    error.value = err instanceof Error ? err.message : '插件包上传失败'
    uploadProgress.value = 0 // 失败归零
  } finally {
    clearInterval(timer)
    // 稍微延迟一下关闭 uploading 状态，让用户能看清 100% 满格的动画效果
    setTimeout(() => {
      uploading.value = false
    }, 400)
  }
}
</script>

<template>
  <section class="panel">
    <!-- 头部介绍 -->
    <div class="intro upload-intro">
      <div class="header-content">
        <p class="eyebrow">Package Registry</p>
        <h2 class="page-title">上传插件包</h2>
        <p class="page-desc">支持 .zip 与 .tar.gz。包根目录必须包含 manifest.yaml 配置。</p>
      </div>
      <a class="secondary-button template-download" href="/api/v1/templates/python-function-package.zip">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="icon-sm">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="7 10 12 15 17 10" />
          <line x1="12" y1="15" x2="12" y2="3" />
        </svg>
        下载插件模板
      </a>
    </div>

    <!-- 提示栏 -->
    <div class="template-hint">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="icon-hint">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="16" x2="12" y2="12"></line>
        <line x1="12" y1="8" x2="12.01" y2="8"></line>
      </svg>
      <div class="hint-text">
        <strong>推荐入口：</strong>
        <span>首次编写插件时，先下载模板，再替换 runtime/main.py 与编译产物。</span>
      </div>
    </div>

    <!-- 核心表单 -->
    <form class="upload-form" @submit.prevent="submit">
      <label class="upload-zone" :class="{ 'has-file': selectedFile, 'is-uploading': uploading }">
        <input type="file" accept=".zip,.gz,.tar.gz" @change="onFileChange" class="hidden-input" :disabled="uploading" />
        
        <!-- 未选择文件时的占位 -->
        <div v-if="!selectedFile" class="upload-placeholder">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="icon-upload">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
            <circle cx="8.5" cy="8.5" r="1.5"></circle>
            <polyline points="21 15 16 10 5 21"></polyline>
          </svg>
          <span class="upload-text">点击选择插件压缩包</span>
          <span class="upload-format">支持 .zip, .tar.gz (不超过系统上限)</span>
        </div>

        <!-- 已选择文件时的展示 (包含进度条) -->
        <div v-else class="file-selected">
          <div class="file-info-row">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="icon-file">
              <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path>
              <polyline points="13 2 13 9 20 9"></polyline>
            </svg>
            <div class="file-info">
              <span class="file-name">{{ selectedFile.name }}</span>
              <span class="file-size">{{ (selectedFile.size / 1024).toFixed(1) }} KB</span>
            </div>
            <span v-if="!uploading" class="file-change-text">点击更换</span>
          </div>

          <!-- 进度条区域 -->
          <div class="progress-wrapper" :class="{ 'show': uploading || uploadProgress > 0 }">
            <div class="progress-track">
              <div class="progress-fill" :style="{ width: uploadProgress + '%' }"></div>
            </div>
            <div class="progress-text" v-if="uploading">
              校验传输中... {{ Math.round(uploadProgress) }}%
            </div>
          </div>
        </div>
      </label>

      <!-- 操作按钮 (优化了尺寸、位置与动效) -->
      <div class="form-actions">
        <button type="submit" class="primary-button" :disabled="uploading || !selectedFile">
          <svg v-if="uploading" class="icon-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 12a9 9 0 1 1-6.219-8.56"></path>
          </svg>
          {{ uploading ? '正在处理...' : '上传并校验' }}
        </button>
      </div>
    </form>

    <!-- 错误反馈 -->
    <div v-if="error" class="error-banner">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="icon-sm">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="8" x2="12" y2="12"></line>
        <line x1="12" y1="16" x2="12.01" y2="16"></line>
      </svg>
      {{ error }}
    </div>

    <!-- 结果展示区 -->
    <div v-if="result" class="result-card">
      <div class="result-header">
        <div class="result-title-row">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="icon-success">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
            <polyline points="22 4 12 14.01 9 11.01"></polyline>
          </svg>
          <h3>校验通过并入库</h3>
        </div>
        <p class="result-subtitle">已登记版本记录。可前往 <RouterLink to="/packages" class="link">插件包列表</RouterLink> 查看。</p>
      </div>

      <dl class="data-grid">
        <div class="data-row">
          <dt>名称</dt>
          <dd class="fw-500">{{ result.name }}</dd>
        </div>
        <div class="data-row">
          <dt>版本</dt>
          <dd><span class="badge">{{ result.version }}</span></dd>
        </div>
        <div class="data-row">
          <dt>状态</dt>
          <dd>
            <span class="status-dot"></span>
            {{ result.status }}
          </dd>
        </div>
        <div class="data-row">
          <dt>包 ID</dt>
          <dd class="code-text">{{ result.package_id }}</dd>
        </div>
        <div class="data-row">
          <dt>版本 ID</dt>
          <dd class="code-text">{{ result.version_id }}</dd>
        </div>
        <div class="data-row">
          <dt>审计 ID</dt>
          <dd class="code-text">{{ result.audit_event_id }}</dd>
        </div>
        <div class="data-row full-width">
          <dt>摘要 (Digest)</dt>
          <dd class="code-text digest-text">{{ result.digest }}</dd>
        </div>
      </dl>
    </div>
  </section>
</template>

<style scoped>
.panel {
  --color-primary: #2563eb;
  --color-primary-hover: #1d4ed8;
  --color-text-main: #0f172a;
  --color-text-muted: #64748b;
  --color-border: #e2e8f0;
  --color-bg-subtle: #f8fafc;
  
  max-width: 800px;
  margin: 0 auto;
  padding: 32px;
  background-color: #ffffff;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.025);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  color: var(--color-text-main);
}

/* --- 头部区域 --- */
.upload-intro {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 24px;
}
.eyebrow { font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: var(--color-text-muted); margin: 0 0 8px 0; }
.page-title { font-size: 24px; font-weight: 600; margin: 0 0 8px 0; color: var(--color-text-main); }
.page-desc { font-size: 14px; color: var(--color-text-muted); margin: 0; }

.secondary-button {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  font-size: 14px; font-weight: 500; border-radius: 6px; cursor: pointer; transition: all 0.2s ease;
  text-decoration: none; white-space: nowrap; padding: 8px 16px;
  background-color: #f1f5f9; color: #334155; border: 1px solid var(--color-border);
}
.secondary-button:hover { background-color: #e2e8f0; }

/* --- 提示框 --- */
.template-hint {
  margin: 0 0 24px; padding: 16px; border: 1px solid #d8e3df; border-radius: 8px; background: #f7faf9;
  color: #314340; display: flex; gap: 12px; align-items: flex-start; font-size: 14px; line-height: 1.5;
}
.icon-hint { width: 20px; height: 20px; color: #437a6b; flex-shrink: 0; margin-top: 2px; }

/* --- 表单与上传区 --- */
.hidden-input { display: none; }

.upload-zone {
  display: block; width: 100%; border: 2px dashed var(--color-border); border-radius: 8px;
  background-color: var(--color-bg-subtle); cursor: pointer; transition: all 0.2s ease;
  padding: 32px 20px; text-align: center; margin-bottom: 24px; box-sizing: border-box;
}
.upload-zone:hover:not(.is-uploading) { border-color: var(--color-primary); background-color: #eff6ff; }
.upload-zone.has-file { border-style: solid; border-color: var(--color-border); padding: 24px 20px; }
.upload-zone.is-uploading { cursor: default; }

.upload-placeholder { display: flex; flex-direction: column; align-items: center; gap: 8px; }
.icon-upload { width: 36px; height: 36px; color: #94a3b8; margin-bottom: 8px; }
.upload-zone:hover:not(.is-uploading) .icon-upload { color: var(--color-primary); }
.upload-text { font-size: 15px; font-weight: 500; color: #334155; }
.upload-format { font-size: 13px; color: var(--color-text-muted); }

/* 已选择文件状态 (含进度条布局) */
.file-selected { display: flex; flex-direction: column; gap: 16px; text-align: left; padding: 0 8px; }
.file-info-row { display: flex; align-items: center; gap: 16px; }
.icon-file { width: 32px; height: 32px; color: var(--color-primary); flex-shrink: 0; }
.file-info { display: flex; flex-direction: column; flex: 1; overflow: hidden; }
.file-name { font-size: 15px; font-weight: 500; color: var(--color-text-main); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.file-size { font-size: 13px; color: var(--color-text-muted); margin-top: 4px; }
.file-change-text { font-size: 13px; color: var(--color-primary); font-weight: 500; }

/* 进度条样式 */
.progress-wrapper { opacity: 0; height: 0; overflow: hidden; transition: all 0.3s ease; }
.progress-wrapper.show { opacity: 1; height: auto; margin-top: 4px; }
.progress-track { width: 100%; height: 6px; background-color: #e2e8f0; border-radius: 3px; overflow: hidden; margin-bottom: 8px; }
.progress-fill { height: 100%; background-color: var(--color-primary); transition: width 0.2s ease-out; }
.progress-text { font-size: 12px; color: var(--color-text-muted); text-align: right; font-variant-numeric: tabular-nums; }

/* --- 操作按钮优化 --- */
.form-actions { 
  display: flex; 
  justify-content: flex-end; 
  /* 增加顶部间距，让按钮脱离拥挤 */
  margin-top: 16px; 
}
.primary-button {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  /* 优化尺寸：加宽内边距，字体微调 */
  padding: 12px 32px; 
  font-size: 15px; 
  font-weight: 600; 
  background-color: var(--color-primary); 
  color: #ffffff; 
  border: none;
  /* 优化圆角与阴影：增加现代感 */
  border-radius: 8px; 
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2);
  cursor: pointer; 
  transition: all 0.2s ease;
  min-width: 160px;
}
.primary-button:hover:not(:disabled) { 
  background-color: var(--color-primary-hover); 
  box-shadow: 0 6px 16px rgba(37, 99, 235, 0.3);
  transform: translateY(-1px); /* 悬浮微升起动效 */
}
.primary-button:disabled { 
  opacity: 0.65; 
  cursor: not-allowed; 
  box-shadow: none;
  transform: none;
}

/* --- 错误反馈 --- */
.error-banner { display: flex; align-items: center; gap: 8px; padding: 12px 16px; background-color: #fef2f2; border: 1px solid #fecaca; color: #b91c1c; border-radius: 8px; font-size: 14px; margin-bottom: 24px; }

/* --- 结果数据区 --- */
.result-card { margin-top: 32px; border-top: 1px solid var(--color-border); padding-top: 24px; }
.result-header { margin-bottom: 20px; }
.result-title-row { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.icon-success { width: 24px; height: 24px; color: #10b981; }
.result-title-row h3 { margin: 0; font-size: 18px; color: var(--color-text-main); }
.result-subtitle { margin: 0; font-size: 14px; color: var(--color-text-muted); }
.link { color: var(--color-primary); text-decoration: none; font-weight: 500; }
.link:hover { text-decoration: underline; }

.data-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin: 0; padding: 20px; background-color: var(--color-bg-subtle); border-radius: 8px; border: 1px solid var(--color-border); }
.data-row { display: flex; flex-direction: column; gap: 4px; }
.data-row.full-width { grid-column: span 2; }
.data-grid dt { font-size: 12px; font-weight: 600; color: var(--color-text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
.data-grid dd { margin: 0; font-size: 14px; color: var(--color-text-main); display: flex; align-items: center; gap: 8px; }
.fw-500 { font-weight: 500; }
.badge { padding: 2px 8px; background-color: #e0e7ff; color: #4338ca; border-radius: 12px; font-size: 12px; font-weight: 600; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; background-color: #10b981; }
.code-text { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size: 13px; color: #475569; }
.digest-text { word-break: break-all; background-color: #ffffff; border: 1px solid var(--color-border); padding: 6px 10px; border-radius: 4px; display: block; width: 100%; margin-top: 4px; }

.icon-sm { width: 16px; height: 16px; }
.icon-spin { width: 16px; height: 16px; animation: spin 1s linear infinite; }
@keyframes spin { 100% { transform: rotate(360deg); } }
</style>