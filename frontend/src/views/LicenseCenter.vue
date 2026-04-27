<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  getLicenseFingerprint,
  getLicenseRevocations,
  getLicenseStatus,
  uploadLicense,
  type FingerprintPayload,
  type LicenseRevocations,
  type LicenseSnapshot,
} from '../api/license'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const status = ref<LicenseSnapshot | null>(null)
const fingerprint = ref<FingerprintPayload | null>(null)
const revocations = ref<LicenseRevocations | null>(null)
const loading = ref(false)
const uploading = ref(false)
const error = ref('')
const success = ref('')

async function refresh() {
  loading.value = true
  error.value = ''
  success.value = ''
  try {
    const [statusPayload, fingerprintPayload, revocationPayload] = await Promise.all([
      getLicenseStatus(),
      getLicenseFingerprint(),
      getLicenseRevocations(),
    ])
    status.value = statusPayload
    fingerprint.value = fingerprintPayload
    revocations.value = revocationPayload
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
    revocations.value = await getLicenseRevocations()
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
  <section class="license-page dark-industrial-theme">
    <!-- 头部区域 -->
    <header class="page-header">
      <div>
        <h1 class="page-title">许可证管理</h1>
        <p class="subtitle text-muted">支持多公钥轮换、撤销清单、宽限期展示与 <code class="cyber-code-inline">license.lic</code> 上传替换。</p>
      </div>
      <div class="actions">
        <button class="btn cyber-btn btn-primary" @click="refresh" :disabled="loading">
          <svg v-if="loading" class="spinner icon-loading" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          {{ loading ? '同步中...' : '刷新状态' }}
        </button>
        <button class="btn cyber-btn btn-outline" @click="downloadFingerprint" :disabled="!fingerprint">导出系统指纹</button>
      </div>
    </header>

    <!-- 消息提示栏 -->
    <div v-if="error" class="cyber-alert alert-error">
      <span class="alert-icon">!</span> {{ error }}
    </div>
    <div v-if="success" class="cyber-alert alert-success">
      <span class="alert-icon">√</span> {{ success }}
    </div>

    <!-- 核心数据网格 -->
    <div class="layout-grid">
      
      <!-- 许可证状态面板 -->
      <article class="cyber-panel card">
        <h2 class="section-title">当前许可证状态</h2>
        <div v-if="loading && !status" class="loading-text blink">读取状态中...</div>
        <div v-else-if="status" class="kv-grid">
          <div class="data-box"><span>运行状态</span><strong :class="status.valid ? 'text-neon-green' : 'text-error'">{{ status.status }}</strong></div>
          <div class="data-box"><span>有效性核验</span><strong :class="status.valid ? 'text-neon-green' : 'text-error'">{{ status.valid ? '已通过' : '未通过' }}</strong></div>
          <div class="data-box"><span>系统只读模式</span><strong :class="status.readonly_mode ? 'text-warning' : 'text-muted'">{{ status.readonly_mode ? '已开启' : '未开启' }}</strong></div>
          <div class="data-box"><span>吊销状态</span><strong :class="status.revoked ? 'text-error' : 'text-neon-green'">{{ status.revoked ? '已吊销' : '正常' }}</strong></div>
          <div class="data-box"><span>授权模式</span><strong>{{ status.grant_mode || '未定义' }}</strong></div>
          <div class="data-box"><span>被授权客户</span><strong>{{ status.customer_name || '未定义' }}</strong></div>
          <div class="data-box"><span>唯一授权码</span><strong class="font-mono text-neon-cyan">{{ status.license_id || '-' }}</strong></div>
          <div class="data-box"><span>签发机构</span><strong>{{ status.issuer || '未知' }}</strong></div>
          <div class="data-box"><span>签名密钥标识</span><strong class="font-mono">{{ status.key_id || '-' }}</strong></div>
          <div class="data-box"><span>签发时间</span><strong>{{ status.issued_at || '-' }}</strong></div>
          <div class="data-box"><span>生效基准时间</span><strong>{{ status.not_before || '-' }}</strong></div>
          <div class="data-box"><span>授权到期时间</span><strong :class="status.grant_mode === 'perpetual' ? 'text-neon-green' : ''">{{ status.not_after || (status.grant_mode === 'perpetual' ? '永久有效' : '-') }}</strong></div>
          <div class="data-box"><span>宽限天数</span><strong>{{ status.grace_days ?? 0 }} 天</strong></div>
          <div class="data-box"><span>宽限期截止</span><strong>{{ status.grace_expires_at || '-' }}</strong></div>
          <div class="data-box wide"><span>状态说明</span><strong :class="status.valid ? 'text-muted' : 'text-error'">{{ status.message }}</strong></div>
        </div>
      </article>

      <!-- 硬件指纹面板 -->
      <article class="cyber-panel card">
        <h2 class="section-title">底层硬件指纹</h2>
        <div v-if="loading && !fingerprint" class="loading-text blink">采集硬件特征中...</div>
        <div v-else-if="fingerprint" class="kv-grid">
          <div class="data-box wide"><span>部署实例特征码</span><strong class="font-mono text-neon-cyan">{{ fingerprint.installation_id }}</strong></div>
          <div class="data-box wide"><span>综合部署特征码</span><strong class="font-mono">{{ fingerprint.deployment_fingerprint }}</strong></div>
          <div class="data-box"><span>网络主机名</span><strong>{{ fingerprint.hostname || '未知' }}</strong></div>
          <div class="data-box"><span>底层机器码</span><strong class="font-mono">{{ fingerprint.machine_id || '未知' }}</strong></div>
          <div class="data-box wide"><span>指纹采集时间</span><strong>{{ fingerprint.generated_at }}</strong></div>
        </div>
      </article>

      <!-- 撤销清单面板 -->
      <article class="cyber-panel card wide-card">
        <h2 class="section-title">本地吊销清单</h2>
        <div v-if="loading && !revocations" class="loading-text blink">比对吊销记录中...</div>
        <div v-else-if="revocations" class="kv-grid">
          <div class="data-box wide"><span>存储路径</span><strong class="font-mono text-muted">{{ revocations.path }}</strong></div>
          <div class="data-box"><span>黑名单数量</span><strong :class="revocations.revoked_license_ids?.length ? 'text-warning' : 'text-neon-green'">{{ revocations.revoked_license_ids?.length || 0 }} 项</strong></div>
          <div class="data-box"><span>上次同步时间</span><strong>{{ revocations.updated_at || '尚未同步' }}</strong></div>
          <div class="data-box wide">
            <span>已被吊销的授权码清单</span>
            <strong class="font-mono block text-error">{{ (revocations.revoked_license_ids || []).join('\n') || '当前环境暂无黑名单数据' }}</strong>
          </div>
        </div>
      </article>

      <!-- 许可证上传面板 -->
      <article class="cyber-panel card wide-card">
        <h2 class="section-title">更新授权文件</h2>
        <p class="subtitle text-muted mb-4">请从厂商获取签发后的 <code class="cyber-code-inline">license.lic</code> 文件，在此处上传以覆盖本地授权。</p>
        
        <div class="upload-container">
          <input 
            type="file" 
            accept=".lic,text/plain" 
            class="cyber-file-input"
            @change="onSelectFile" 
            :disabled="uploading || !auth.can('user.update')" 
          />
        </div>
        
        <p class="hint mt-3">
          权限管控：依赖核心体系 <code class="cyber-code-inline">user.update</code> 权限点，越权操作将被拦截。
        </p>
      </article>

      <!-- 详细授权参数面板 -->
      <article v-if="status && status.entitlements" class="cyber-panel card wide-card">
        <h2 class="section-title">进阶资源配额</h2>
        <pre class="cyber-code-block">{{ JSON.stringify(status.entitlements, null, 2) }}</pre>
      </article>

    </div>
  </section>
</template>

<style scoped>
/* ========================================================
   1. 全局变量 (暗黑工业/赛博风) - 保持不变
   ======================================================== */
.dark-industrial-theme {
  --bg-app: #030a12;
  --bg-panel: rgba(6, 21, 37, 0.85);
  --bg-input: #020810;
  
  --border-main: #14304f;
  --border-light: #1e4570;
  
  --accent-cyan: #00e5ff;
  --accent-cyan-glow: rgba(0, 229, 255, 0.4);
  --accent-green: #00ff88;
  --accent-red: #ff3366;
  --accent-warning: #ffaa00;
  
  --text-main: #d1e4fb;
  --text-bright: #ffffff;
  --text-muted: #537599;

  background-color: var(--bg-app);
  background-image: 
    linear-gradient(rgba(20, 48, 79, 0.2) 1px, transparent 1px),
    linear-gradient(90deg, rgba(20, 48, 79, 0.2) 1px, transparent 1px);
  background-size: 30px 30px;
  color: var(--text-main);
  font-family: 'Rajdhani', 'Segoe UI', 'Roboto Mono', 'Microsoft YaHei', sans-serif;
  padding: 24px;
  min-height: 100vh;
  box-sizing: border-box;
}

/* 基础原子类 */
.text-muted { color: var(--text-muted); }
.text-error { color: var(--accent-red); text-shadow: 0 0 5px rgba(255,51,102,0.4); }
.text-warning { color: var(--accent-warning); }
.text-neon-green { color: var(--accent-green); text-shadow: 0 0 5px rgba(0,255,136,0.4); }
.text-neon-cyan { color: var(--accent-cyan); text-shadow: 0 0 5px var(--accent-cyan-glow); }
.font-mono { font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; }
.block { display: block; white-space: pre-wrap; word-break: break-all; }
.mb-4 { margin-bottom: 16px; }
.mt-3 { margin-top: 12px; }
.blink { animation: blinker 1.5s linear infinite; }
@keyframes blinker { 50% { opacity: 0.3; } }

/* ========================================================
   2. 赛博工业风面板核心样式 (Corner Brackets)
   ======================================================== */
.cyber-panel {
  position: relative;
  background: var(--bg-panel);
  backdrop-filter: blur(4px);
  border: 1px solid var(--border-main);
  box-shadow: inset 0 0 20px rgba(0,0,0,0.5);
  padding: 20px;
  transition: box-shadow 0.3s, border-color 0.3s;
}
/* 左上与右下青色折角 */
.cyber-panel::before,
.cyber-panel::after {
  content: ''; position: absolute; width: 12px; height: 12px; pointer-events: none;
}
.cyber-panel::before {
  top: -1px; left: -1px;
  border-top: 2px solid var(--accent-cyan);
  border-left: 2px solid var(--accent-cyan);
  box-shadow: -2px -2px 6px var(--accent-cyan-glow);
}
.cyber-panel::after {
  bottom: -1px; right: -1px;
  border-bottom: 2px solid var(--accent-cyan);
  border-right: 2px solid var(--accent-cyan);
  box-shadow: 2px 2px 6px var(--accent-cyan-glow);
}

/* ========================================================
   3. 头部区域 & 标题
   ======================================================== */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 24px;
  border-bottom: 1px solid var(--border-main);
  padding-bottom: 16px;
  gap: 16px;
}
.page-title { margin: 0 0 8px 0; font-size: 26px; font-weight: 700; color: var(--text-bright); letter-spacing: 2px; }
.subtitle { margin: 0; font-size: 14px; }
.section-title {
  font-size: 16px; color: var(--text-bright);
  border-left: 3px solid var(--accent-cyan);
  padding-left: 10px; margin-top: 0; margin-bottom: 16px; letter-spacing: 1px;
}

/* ========================================================
   4. 按钮系统
   ======================================================== */
.actions { display: flex; gap: 12px; flex-wrap: wrap; }
.btn {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 8px 16px; min-height: 38px;
  font-size: 13px; font-weight: 600; letter-spacing: 1px;
  cursor: pointer; transition: all 0.2s ease; outline: none; font-family: inherit;
}
.cyber-btn {
  background: transparent; border: 1px solid var(--border-light);
  color: var(--text-main); position: relative; overflow: hidden;
}
.cyber-btn::before {
  content: ''; position: absolute; top:0; left:0; right:0; bottom:0;
  background: var(--accent-cyan); opacity: 0; transition: opacity 0.2s; z-index: -1;
}
.btn-primary {
  border-color: var(--accent-cyan); color: var(--accent-cyan);
  box-shadow: inset 0 0 8px rgba(0, 229, 255, 0.1);
}
.btn-primary:hover:not(:disabled) { color: #000; box-shadow: 0 0 15px var(--accent-cyan-glow); }
.btn-primary:hover:not(:disabled)::before { opacity: 1; }

.btn-outline:hover:not(:disabled) {
  border-color: var(--text-bright); color: var(--text-bright);
  background: rgba(255,255,255,0.05);
}
.btn:disabled { opacity: 0.4; cursor: not-allowed; border-color: var(--border-main); color: var(--text-muted); }

/* ========================================================
   5. 消息提示栏 (Banners)
   ======================================================== */
.cyber-alert {
  display: flex; align-items: center; padding: 12px 16px;
  margin-bottom: 24px; border: 1px solid; font-size: 14px;
}
.alert-icon { font-weight: bold; font-size: 16px; margin-right: 12px; font-family: monospace; }
.alert-error {
  background: rgba(255, 51, 102, 0.1); border-color: var(--accent-red);
  color: var(--accent-red); box-shadow: 0 0 10px rgba(255, 51, 102, 0.2);
}
.alert-success {
  background: rgba(0, 255, 136, 0.1); border-color: var(--accent-green);
  color: var(--accent-green); box-shadow: 0 0 10px rgba(0, 255, 136, 0.2);
}

/* ========================================================
   6. 核心数据网格 (Grid Layout)
   ======================================================== */
.layout-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}
.wide-card { grid-column: 1 / -1; }

.kv-grid {
  display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px;
}
.data-box {
  background: rgba(0, 0, 0, 0.3); border: 1px solid var(--border-main);
  padding: 12px 14px; display: flex; flex-direction: column; gap: 6px;
  transition: border-color 0.2s;
}
.data-box:hover { border-color: var(--border-light); }
.data-box span { font-size: 12px; color: var(--text-muted); }
.data-box strong { font-size: 14px; color: var(--text-bright); overflow-wrap: anywhere; line-height: 1.4; }
.data-box.wide { grid-column: 1 / -1; }

/* ========================================================
   7. 强化版上传区块 —— 更显眼、专业、赛博工业风
   ======================================================== */

/* 整个上传面板（当卡片包含 .upload-container 时额外增加光效） */
.cyber-panel:has(.upload-container) {
  border-color: var(--accent-cyan);
  box-shadow: 0 0 18px rgba(0, 229, 255, 0.3), inset 0 0 12px rgba(0, 229, 255, 0.1);
  animation: borderPulse 3s infinite alternate;
}
@keyframes borderPulse {
  0% { border-color: var(--accent-cyan); box-shadow: 0 0 8px rgba(0, 229, 255, 0.2); }
  100% { border-color: #5effe6; box-shadow: 0 0 28px rgba(0, 229, 255, 0.6); }
}

/* 上传区块内的标题 */
.cyber-panel:has(.upload-container) .section-title {
  font-size: 20px;
  background: linear-gradient(135deg, #ffffff, var(--accent-cyan));
  background-clip: text;
  -webkit-background-clip: text;
  color: transparent;
  text-shadow: 0 0 8px var(--accent-cyan-glow);
  letter-spacing: 2px;
  border-left-width: 4px;
  padding-left: 14px;
  margin-bottom: 20px;
}

/* 上传区块内的说明文字（subtitle） */
.cyber-panel:has(.upload-container) .subtitle {
  font-size: 15px;
  color: #bbddff;
  background: rgba(0, 229, 255, 0.05);
  padding: 8px 12px;
  border-radius: 6px;
  border-left: 3px solid var(--accent-cyan);
  margin-bottom: 20px;
}

/* 上传容器本身 */
.upload-container {
  display: flex;
  align-items: center;
  margin: 16px 0 12px;
  background: rgba(0, 229, 255, 0.02);
  border-radius: 8px;
  padding: 4px;
  transition: all 0.2s;
}

/* 文件输入框整体样式 */
.cyber-file-input {
  width: 100%;
  background: #010a12;
  border: 1px solid var(--accent-cyan);
  border-radius: 8px;
  color: #ffffff;   /* 纯白色 */
  font-size: 14px;
  padding: 8px 12px;
  outline: none;
  font-family: 'Rajdhani', monospace;
  transition: 0.2s;
  box-shadow: inset 0 0 6px rgba(0,0,0,0.5);
}
.cyber-file-input:hover:not(:disabled) {
  border-color: #5effe6;
  box-shadow: 0 0 10px var(--accent-cyan-glow);
}
.cyber-file-input:focus-within:not(:disabled) {
  border-color: #ffffff;
  box-shadow: 0 0 16px var(--accent-cyan);
}

/* 自定义上传按钮（原生按钮样式加强） */
.cyber-file-input::file-selector-button {
  background: linear-gradient(135deg, #00b8d4, #00697e);
  border: none;
  border-radius: 6px;
  color: #ffffff;
  font-weight: bold;
  font-size: 14px;
  padding: 8px 24px;
  margin-right: 20px;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  font-family: 'Rajdhani', monospace;
  box-shadow: 0 0 6px #00e5ff;
  cursor: pointer;
  transition: 0.2s;
}
.cyber-file-input::file-selector-button:hover {
  background: linear-gradient(135deg, #00e5ff, #0088aa);
  color: #00d6ef;
  box-shadow: 0 0 14px #00e5ff;
  transform: scale(1.02);
}
.cyber-file-input:disabled::file-selector-button {
  opacity: 0.5;
  filter: grayscale(0.4);
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

/* 禁用状态的输入框 */
.cyber-file-input:disabled {
  opacity: 0.7;
  border-color: var(--border-main);
  cursor: not-allowed;
}

/* 权限提示行 */
.cyber-panel:has(.upload-container) .hint {
  font-size: 13px;
  padding: 8px 12px;
  background: rgba(0, 0, 0, 0.5);
  border-radius: 6px;
  border-top: 1px dashed var(--accent-cyan);
  color: #8db4e0;
  display: inline-block;
  width: auto;
  margin-top: 16px;
}
.cyber-panel:has(.upload-container) .hint code {
  background: #00161f;
  color: var(--accent-cyan);
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: bold;
}

/* 其他原有代码块样式 */
.cyber-code-inline {
  background: rgba(0,0,0,0.5); padding: 2px 6px; border: 1px solid var(--border-main);
  font-family: monospace; color: var(--accent-cyan); font-size: 13px;
}
.cyber-code-block {
  margin: 0; padding: 16px; background: #010408;
  border: 1px solid var(--border-main); border-left: 2px solid var(--text-muted);
  font-family: monospace; font-size: 13px; color: #a5b4c5;
  overflow: auto; white-space: pre-wrap; word-break: break-all;
}

/* 加载动画 */
.icon-loading { animation: spin 1s linear infinite; width: 14px; height: 14px; margin-right: 6px; }
@keyframes spin { 100% { transform: rotate(360deg); } }
.loading-text { font-family: monospace; color: var(--accent-cyan); padding: 12px 0; }

/* 响应式 */
@media (max-width: 960px) {
  .layout-grid, .kv-grid, .page-header { grid-template-columns: 1fr; display: flex; flex-direction: column; }
  .actions { justify-content: flex-start; width: 100%; }
}
.cyber-file-input {
  color: #ffffff !important;
}

.cyber-file-input::file-selector-button,
.cyber-file-input::-webkit-file-upload-button {
  color: #ffffff !important;
  background: linear-gradient(135deg, #00b8d4, #00697e);
  border: none;
  border-radius: 6px;
  font-size: 14px;
  padding: 8px 24px;
  margin-right: 20px;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  font-family: 'Rajdhani', monospace;
  cursor: pointer;
  transition: 0.2s;
}

.cyber-file-input::file-selector-button:hover,
.cyber-file-input::-webkit-file-upload-button:hover {
  background: linear-gradient(135deg, #00e5ff, #0088aa);
  box-shadow: 0 0 10px #00e5ff;
}
</style>