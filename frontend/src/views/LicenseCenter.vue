<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getLicenseFingerprint, getLicenseStatus, uploadLicense, type FingerprintPayload, type LicenseSnapshot } from '../api/license'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const status = ref<LicenseSnapshot | null>(null)
const fingerprint = ref<FingerprintPayload | null>(null)
const loading = ref(false)
const uploading = ref(false)
const error = ref('')
const success = ref('')

async function refresh() {
  loading.value = true
  error.value = ''
  success.value = ''
  try {
    const [statusPayload, fingerprintPayload] = await Promise.all([
      getLicenseStatus(),
      getLicenseFingerprint(),
    ])
    status.value = statusPayload
    fingerprint.value = fingerprintPayload
  } catch (err) {
    error.value = err instanceof Error ? err.message : '许可证信息加载失败'
  } finally {
    loading.value = false
  }
}

async function onSelectFile(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.lic')) {
    error.value = '仅支持上传 .lic 许可证文件'
    return
  }
  uploading.value = true
  error.value = ''
  success.value = ''
  try {
    const result = await uploadLicense(file)
    status.value = result
    success.value = '许可证上传成功'
    fingerprint.value = await getLicenseFingerprint()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '许可证上传失败'
  } finally {
    uploading.value = false
    target.value = ''
  }
}

function downloadFingerprint() {
  if (!fingerprint.value) return
  const blob = new Blob([JSON.stringify(fingerprint.value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'license-fingerprint.json'
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(refresh)
</script>

<template>
  <section class="license-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">License Management</p>
        <h1>许可证管理</h1>
        <p class="subtitle">查看许可证状态、下载部署指纹并上传新的 <code>license.lic</code> 文件。</p>
      </div>
      <div class="actions">
        <button class="primary" @click="refresh" :disabled="loading">{{ loading ? '刷新中…' : '刷新状态' }}</button>
        <button class="secondary" @click="downloadFingerprint" :disabled="!fingerprint">下载指纹</button>
      </div>
    </header>

    <p v-if="error" class="banner error">{{ error }}</p>
    <p v-if="success" class="banner success">{{ success }}</p>

    <div class="grid">
      <article class="card">
        <h2>许可证状态</h2>
        <div v-if="status" class="kv-grid">
          <div><span>状态</span><strong>{{ status.status }}</strong></div>
          <div><span>有效</span><strong>{{ status.valid ? 'Yes' : 'No' }}</strong></div>
          <div><span>只读模式</span><strong>{{ status.readonly_mode ? 'Yes' : 'No' }}</strong></div>
          <div><span>授权类型</span><strong>{{ status.grant_mode || '-' }}</strong></div>
          <div><span>客户</span><strong>{{ status.customer_name || '-' }}</strong></div>
          <div><span>许可证 ID</span><strong>{{ status.license_id || '-' }}</strong></div>
          <div><span>签发方</span><strong>{{ status.issuer || '-' }}</strong></div>
          <div><span>Key ID</span><strong>{{ status.key_id || '-' }}</strong></div>
          <div><span>签发时间</span><strong>{{ status.issued_at || '-' }}</strong></div>
          <div><span>生效起点</span><strong>{{ status.not_before || '-' }}</strong></div>
          <div><span>到期时间</span><strong>{{ status.not_after || (status.grant_mode === 'perpetual' ? '永久' : '-') }}</strong></div>
          <div class="wide"><span>说明</span><strong>{{ status.message }}</strong></div>
        </div>
      </article>

      <article class="card">
        <h2>部署指纹</h2>
        <div v-if="fingerprint" class="kv-grid">
          <div><span>Installation ID</span><strong>{{ fingerprint.installation_id }}</strong></div>
          <div><span>Hostname</span><strong>{{ fingerprint.hostname || '-' }}</strong></div>
          <div><span>Machine ID</span><strong class="mono">{{ fingerprint.machine_id || '-' }}</strong></div>
          <div class="wide"><span>Deployment Fingerprint</span><strong class="mono">{{ fingerprint.deployment_fingerprint }}</strong></div>
          <div><span>生成时间</span><strong>{{ fingerprint.generated_at }}</strong></div>
        </div>
      </article>

      <article class="card wide-card">
        <h2>上传许可证</h2>
        <p class="subtitle">请从发行方获取签发后的 <code>license.lic</code> 文件，并在此上传覆盖当前许可证。</p>
        <input type="file" accept=".lic,text/plain" @change="onSelectFile" :disabled="uploading || !auth.can('user.update')" />
      </article>

      <article v-if="status" class="card wide-card">
        <h2>授权参数</h2>
        <pre>{{ JSON.stringify(status.entitlements, null, 2) }}</pre>
      </article>
    </div>
  </section>
</template>

<style scoped>
/* ==========================================
   1. 设计令牌 (Design Tokens) - 现代化变量定义
   ========================================== */
.license-page {
  /* 主色调：克制、专业的工业绿灰调 */
  --color-primary: #115e59;
  --color-primary-hover: #0f766e;
  --color-success: #059669;
  --color-warning: #d97706;
  --color-danger: #dc2626;
  
  /* 表面与背景 */
  --color-bg-base: #f8fafc;
  --color-bg-surface: #ffffff;
  --color-bg-subtle: #f1f5f9;
  --color-bg-muted: #e2e8f0;

  /* 边框 */
  --color-border: #cbd5e1;
  --color-border-hover: #94a3b8;
  --color-border-focus: #115e59;

  /* 文本层次 */
  --color-text-main: #0f172a;
  --color-text-muted: #475569;
  --color-text-light: #64748b;

  /* 空间与圆角 */
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;

  /* 多层级阴影 (Elevation) */
  --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
  --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -4px rgba(0, 0, 0, 0.05);
  --shadow-focus: 0 0 0 3px rgba(17, 94, 89, 0.15);

  --transition-all: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);

  display: flex;
  flex-direction: column;
  gap: 24px;
  max-width: 1440px;
  margin: 0 auto;
  font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
  color: var(--color-text-main);
}

/* ==========================================
   2. 页面布局与头部 (Page Header)
   ========================================== */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--color-border);
}

.page-header > div {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.eyebrow {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--color-primary);
}

.page-header h1 {
  margin: 0;
  font-size: 28px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--color-text-main);
}

.subtitle {
  margin: 0;
  font-size: 15px;
  color: var(--color-text-muted);
}

/* ==========================================
   3. 交互组件体系 (Buttons & Actions)
   ========================================== */
.actions {
  display: flex;
  gap: 12px;
}

button {
  font-family: inherit;
  transition: var(--transition-all);
}

.primary, .secondary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 18px;
  border-radius: var(--radius-sm);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  outline: none;
  border: 1px solid transparent;
  white-space: nowrap;
}

.primary {
  background: var(--color-primary);
  color: #ffffff;
  box-shadow: var(--shadow-sm);
}

.primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.secondary {
  background: var(--color-bg-surface);
  border-color: var(--color-border);
  color: var(--color-text-main);
  box-shadow: var(--shadow-sm);
}

.secondary:hover:not(:disabled) {
  background: var(--color-bg-subtle);
  border-color: var(--color-border-hover);
}

button:focus-visible { box-shadow: var(--shadow-focus); }
button:disabled { opacity: 0.5; cursor: not-allowed; transform: none; box-shadow: none; }

/* ==========================================
   4. 横幅提示 (Banners)
   ========================================== */
.banner {
  margin: 0;
  padding: 14px 16px;
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 600;
  box-shadow: var(--shadow-sm);
  border: 1px solid transparent;
}

.banner.error {
  background: #fef2f2;
  border-color: #fecaca;
  color: #b91c1c;
}

.banner.success {
  background: #f0fdf4;
  border-color: #bbf7d0;
  color: #15803d;
}

/* ==========================================
   5. 网格与卡片 (Grid & Cards)
   ========================================== */
.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 24px;
}

.card {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  padding: 24px;
  display: flex;
  flex-direction: column;
  transition: var(--transition-all);
  box-shadow: var(--shadow-sm);
}

.card:hover {
  border-color: var(--color-border-hover);
  box-shadow: var(--shadow-lg);
  transform: translateY(-2px);
}

.card h2 {
  margin: 0 0 20px 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text-main);
  line-height: 1.2;
}

.wide-card {
  grid-column: 1 / -1;
}

/* ==========================================
   6. 键值对只读网格 (Key-Value Grid)
   ========================================== */
.kv-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.kv-grid > div {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 16px;
  background: var(--color-bg-subtle);
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  transition: var(--transition-all);
}

.kv-grid > div:hover {
  background: var(--color-bg-surface);
  border-color: var(--color-border);
  box-shadow: var(--shadow-sm);
}

.kv-grid span {
  color: var(--color-text-muted);
  font-size: 13px;
  font-weight: 500;
}

.kv-grid strong {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-main);
  overflow-wrap: anywhere;
  word-break: break-all;
}

.kv-grid .wide {
  grid-column: 1 / -1;
}

/* ==========================================
   7. 表单组件与代码块 (Forms & Typography)
   ========================================== */
code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  background: var(--color-bg-subtle);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  color: var(--color-primary);
  border: 1px solid var(--color-border);
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 13px !important;
  color: var(--color-text-main);
}

pre {
  margin: 0;
  padding: 20px;
  background: #1e293b; /* 采用深色面板，更具控制台专业质感 */
  color: #f8fafc;
  border-radius: var(--radius-lg);
  overflow-x: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 13px;
  line-height: 1.5;
  box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.1);
}

input[type="file"] {
  display: block;
  width: 100%;
  margin: 20px 0 16px 0;
  padding: 10px;
  font-family: inherit;
  font-size: 14px;
  color: var(--color-text-main);
  background: var(--color-bg-subtle);
  border: 1px dashed var(--color-border-hover);
  border-radius: var(--radius-md);
  transition: var(--transition-all);
  cursor: pointer;
}

input[type="file"]:hover:not(:disabled) {
  border-color: var(--color-primary);
  background: #f0fdfa; /* 极弱强调色背景 */
}

input[type="file"]:focus-visible {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

/* 伪类定制：美化原生文件选择按钮 */
input[type="file"]::file-selector-button {
  margin-right: 16px;
  padding: 8px 16px;
  border-radius: var(--radius-sm);
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  color: var(--color-text-main);
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  transition: var(--transition-all);
  box-shadow: var(--shadow-sm);
}

input[type="file"]::file-selector-button:hover {
  background: var(--color-bg-subtle);
  border-color: var(--color-border-hover);
}

.hint {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 6px;
}

/* ==========================================
   8. 响应式适配 (Responsive)
   ========================================== */
@media (max-width: 960px) {
  .grid, .kv-grid {
    grid-template-columns: 1fr;
  }
  .page-header {
    flex-direction: column;
    align-items: flex-start;
  }
  .actions {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
