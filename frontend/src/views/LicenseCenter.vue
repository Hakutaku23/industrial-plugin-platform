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
        <p class="hint">上传权限：复用当前权限体系中的 <code>user.update</code>，默认仅管理员可操作。</p>
      </article>

      <article v-if="status" class="card wide-card">
        <h2>授权参数</h2>
        <pre>{{ JSON.stringify(status.entitlements, null, 2) }}</pre>
      </article>
    </div>
  </section>
</template>

<style scoped>
.license-page { display: grid; gap: 20px; }
.page-header { display: flex; justify-content: space-between; gap: 16px; align-items: flex-end; }
.page-header h1 { margin: 0; font-size: 28px; }
.eyebrow { margin: 0 0 6px; color: #64748b; font-size: 12px; text-transform: uppercase; }
.subtitle { color: #64748b; }
.actions { display: flex; gap: 12px; }
.primary, .secondary { min-height: 40px; padding: 0 16px; border-radius: 8px; border: 1px solid #cbd5e1; cursor: pointer; }
.primary { background: #2563eb; color: #fff; border-color: #2563eb; }
.secondary { background: #fff; color: #0f172a; }
.banner { margin: 0; padding: 12px 14px; border-radius: 8px; }
.banner.error { background: #fee2e2; color: #991b1b; }
.banner.success { background: #dcfce7; color: #166534; }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.card { background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; }
.card h2 { margin-top: 0; }
.wide-card { grid-column: 1 / -1; }
.kv-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.kv-grid > div { display: grid; gap: 4px; padding: 12px; background: #f8fafc; border-radius: 8px; }
.kv-grid span { color: #64748b; font-size: 12px; }
.kv-grid strong { font-size: 14px; color: #0f172a; overflow-wrap: anywhere; }
.kv-grid .wide { grid-column: 1 / -1; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
pre { margin: 0; padding: 16px; background: #f8fafc; border-radius: 8px; overflow: auto; }
.hint { color: #64748b; font-size: 13px; }
@media (max-width: 960px) {
  .grid, .kv-grid, .page-header { grid-template-columns: 1fr; display: grid; }
  .actions { justify-content: flex-start; }
}
</style>
