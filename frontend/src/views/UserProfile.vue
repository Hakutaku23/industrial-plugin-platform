<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getMyPermissionMatrix, updateMyProfile, type PermissionRecord } from '../api/auth'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const success = ref('')
const activeTab = ref<'profile' | 'security' | 'permissions'>('profile')

const profileForm = ref({
  display_name: '',
  email: '',
  avatar_url: '',
})

const passwordForm = ref({
  current_password: '',
  new_password: '',
  confirm_password: '',
})

const ownedPermissions = ref<PermissionRecord[]>([])
const missingPermissions = ref<PermissionRecord[]>([])

interface PermissionGroup {
  module: string
  moduleLabel: string
  items: PermissionRecord[]
}

const avatarText = computed(() => {
  const source = profileForm.value.display_name || auth.user?.username || 'U'
  return source.trim().slice(0, 1).toUpperCase()
})
const ownedPermissionGroups = computed(() => groupPermissions(ownedPermissions.value))
const missingPermissionGroups = computed(() => groupPermissions(missingPermissions.value))

function groupPermissions(items: PermissionRecord[]): PermissionGroup[] {
  const groups = new Map<string, PermissionGroup>()
  for (const item of items) {
    const key = item.module || item.code.split('.')[0] || 'other'
    const moduleLabel = item.module_label || key
    if (!groups.has(key)) {
      groups.set(key, { module: key, moduleLabel, items: [] })
    }
    groups.get(key)?.items.push(item)
  }
  return Array.from(groups.values()).map((group) => ({
    ...group,
    items: [...group.items].sort((a, b) => permissionTitle(a).localeCompare(permissionTitle(b), 'zh-Hans-CN')),
  }))
}

function permissionTitle(item: PermissionRecord): string {
  return item.label || [item.module_label, item.action_label].filter(Boolean).join(' / ') || item.code
}

function hydrateProfile() {
  profileForm.value = {
    display_name: auth.user?.display_name ?? '',
    email: auth.user?.email ?? '',
    avatar_url: auth.user?.avatar_url ?? '',
  }
}

async function loadPermissions() {
  const payload = await getMyPermissionMatrix()
  ownedPermissions.value = payload.owned
  missingPermissions.value = payload.missing
}

async function saveProfile() {
  saving.value = true
  error.value = ''
  success.value = ''
  try {
    await updateMyProfile({
      display_name: profileForm.value.display_name.trim(),
      email: profileForm.value.email.trim() || null,
      avatar_url: profileForm.value.avatar_url.trim() || null,
    })
    await auth.refreshMe()
    hydrateProfile()
    success.value = '个人资料已更新。'
  } catch (err) {
    error.value = err instanceof Error ? err.message : '个人资料更新失败'
  } finally {
    saving.value = false
  }
}

async function savePassword() {
  error.value = ''
  success.value = ''
  if (!passwordForm.value.current_password.trim()) {
    error.value = '请输入当前密码。'
    return
  }
  if (!passwordForm.value.new_password.trim() || passwordForm.value.new_password.length < 8) {
    error.value = '新密码至少需要 8 位。'
    return
  }
  if (passwordForm.value.new_password !== passwordForm.value.confirm_password) {
    error.value = '两次输入的新密码不一致。'
    return
  }

  saving.value = true
  try {
    await updateMyProfile({
      current_password: passwordForm.value.current_password,
      new_password: passwordForm.value.new_password,
    })
    passwordForm.value = { current_password: '', new_password: '', confirm_password: '' }
    success.value = '密码已更新。'
  } catch (err) {
    error.value = err instanceof Error ? err.message : '密码修改失败'
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  loading.value = true
  try {
    await auth.bootstrap()
    await auth.refreshMe()
    hydrateProfile()
    await loadPermissions()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '个人中心加载失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="profile-page dark-industrial-theme">
    <!-- 头部区域 -->
    <header class="page-heading">
      <div>
        <h2 class="page-title">账户控制台</h2>
        <p class="subtitle text-muted">在这里管理您的身份标识、凭证信息与系统权限矩阵。</p>
      </div>
    </header>

    <!-- 消息提示栏 -->
    <div v-if="error" class="cyber-alert alert-error">
      <span class="alert-icon">!</span> {{ error }}
    </div>
    <div v-if="success" class="cyber-alert alert-success">
      <span class="alert-icon">√</span> {{ success }}
    </div>
    <div v-if="loading" class="loading-text blink">> 正在读取操作员档案...</div>

    <div class="profile-shell" v-if="!loading && auth.user">
      
      <!-- 侧边栏：操作员名片 & 导航 -->
      <aside class="cyber-panel profile-sidebar">
        <div class="avatar-panel">
          <div v-if="profileForm.avatar_url" class="avatar-image-wrap cyber-border">
            <img :src="profileForm.avatar_url" alt="avatar" class="avatar-image" />
          </div>
          <div v-else class="avatar-fallback cyber-border">{{ avatarText }}</div>
          
          <strong class="operator-name">{{ auth.user.display_name }}</strong>
          <span class="font-mono text-muted operator-id">ID: {{ auth.user.username }}</span>
          <span class="status-badge mt-2">{{ auth.user.roles[0] || '默认节点' }}</span>
        </div>

        <nav class="tab-list">
          <button type="button" class="cyber-tab-btn" :class="{ active: activeTab === 'profile' }" @click="activeTab = 'profile'">
            身份信息
          </button>
          <button type="button" class="cyber-tab-btn" :class="{ active: activeTab === 'security' }" @click="activeTab = 'security'">
            密码安全
          </button>
          <button type="button" class="cyber-tab-btn" :class="{ active: activeTab === 'permissions' }" @click="activeTab = 'permissions'">
            系统权限矩阵
          </button>
        </nav>
      </aside>

      <!-- 右侧：内容区 -->
      <div class="profile-content">
        
        <!-- 身份资料面板 -->
        <div v-if="activeTab === 'profile'" class="cyber-panel content-card">
          <h3 class="section-title">更新操作员档案</h3>
          <div class="form-grid">
            <div class="input-group">
              <label>显示名称</label>
              <input v-model="profileForm.display_name" class="cyber-input" placeholder="输入您的常用称呼" />
            </div>
            <div class="input-group">
              <label>联络邮箱</label>
              <input v-model="profileForm.email" type="email" class="cyber-input" placeholder="example@domain.com" />
            </div>
            <div class="input-group full-width">
              <label>标识图像链接 (Avatar URL)</label>
              <input v-model="profileForm.avatar_url" class="cyber-input" placeholder="https://..." />
            </div>
          </div>
          <div class="action-row">
            <button type="button" class="btn cyber-btn btn-primary" @click="saveProfile" :disabled="saving">
              {{ saving ? '档案覆写中...' : '覆写档案' }}
            </button>
          </div>
        </div>

        <!-- 密码安全面板 -->
        <div v-else-if="activeTab === 'security'" class="cyber-panel content-card">
          <h3 class="section-title">重置访问凭证</h3>
          <div class="form-grid">
            <div class="input-group">
              <label>当前凭证 (密码)</label>
              <input v-model="passwordForm.current_password" type="password" class="cyber-input" placeholder="******" />
            </div>
            <div class="input-group">
              <label>新凭证 (至少 8 位)</label>
              <input v-model="passwordForm.new_password" type="password" class="cyber-input" minlength="8" placeholder="******" />
            </div>
            <div class="input-group full-width">
              <label>校验新凭证</label>
              <input v-model="passwordForm.confirm_password" type="password" class="cyber-input" minlength="8" placeholder="******" />
            </div>
          </div>
          <div class="action-row">
            <button type="button" class="btn cyber-btn btn-primary" @click="savePassword" :disabled="saving">
              {{ saving ? '加密传输中...' : '下发新凭证' }}
            </button>
          </div>
        </div>

        <!-- 权限矩阵面板 -->
        <div v-else class="cyber-panel content-card permissions-card">
          <h3 class="section-title">当前系统授权范围</h3>
          <div class="permission-columns">
            
            <!-- 已拥有权限列 -->
            <section class="permission-column cyber-sub-panel granted-col">
              <header class="col-header">
                <strong class="text-neon-green">已授权节点</strong>
                <span class="count-badge green-badge">{{ ownedPermissions.length }} 项</span>
              </header>
              <div class="permission-list grouped">
                <div v-for="group in ownedPermissionGroups" :key="group.module" class="permission-group">
                  <div class="permission-group-title">
                    <strong class="text-muted">{{ group.moduleLabel }}</strong>
                  </div>
                  <div v-for="item in group.items" :key="item.code" class="data-box permission-item">
                    <span class="cyber-icon icon-success">[√]</span>
                    <div class="item-details">
                      <strong class="text-bright">{{ permissionTitle(item) }}</strong>
                      <code class="font-mono text-neon-cyan">{{ item.code }}</code>
                      <p class="text-muted">{{ item.description || '暂无说明' }}</p>
                    </div>
                  </div>
                </div>
              </div>
            </section>

            <!-- 未拥有权限列 -->
            <section class="permission-column cyber-sub-panel missing-col">
              <header class="col-header">
                <strong class="text-error">未授权节点</strong>
                <span class="count-badge red-badge">{{ missingPermissions.length }} 项</span>
              </header>
              <div class="permission-list grouped">
                <div v-for="group in missingPermissionGroups" :key="group.module" class="permission-group">
                  <div class="permission-group-title">
                    <strong class="text-muted">{{ group.moduleLabel }}</strong>
                  </div>
                  <div v-for="item in group.items" :key="item.code" class="data-box permission-item">
                    <span class="cyber-icon icon-danger">[×]</span>
                    <div class="item-details">
                      <strong class="text-bright">{{ permissionTitle(item) }}</strong>
                      <code class="font-mono text-error">{{ item.code }}</code>
                      <p class="text-muted">{{ item.description || '需要向管理节点申请' }}</p>
                    </div>
                  </div>
                </div>
              </div>
            </section>

          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* ========================================================
   1. 全局变量 (暗黑工业/赛博风)
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
.text-bright { color: var(--text-bright); }
.text-error { color: var(--accent-red); text-shadow: 0 0 5px rgba(255,51,102,0.4); }
.text-neon-green { color: var(--accent-green); text-shadow: 0 0 5px rgba(0,255,136,0.4); }
.text-neon-cyan { color: var(--accent-cyan); text-shadow: 0 0 5px var(--accent-cyan-glow); }
.font-mono { font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; }
.mt-2 { margin-top: 8px; }
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

.cyber-border {
  border: 1px solid var(--border-main);
  box-shadow: inset 0 0 10px rgba(0, 229, 255, 0.1);
}

/* ========================================================
   3. 头部与消息提示
   ======================================================== */
.page-heading {
  margin-bottom: 24px;
  border-bottom: 1px solid var(--border-main);
  padding-bottom: 16px;
}
.page-title { margin: 0 0 8px 0; font-size: 26px; font-weight: 700; color: var(--text-bright); letter-spacing: 2px; }
.subtitle { margin: 0; font-size: 14px; }
.section-title {
  font-size: 16px; color: var(--text-bright);
  border-left: 3px solid var(--accent-cyan);
  padding-left: 10px; margin-top: 0; margin-bottom: 20px; letter-spacing: 1px;
}

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
.loading-text { font-family: monospace; color: var(--accent-cyan); padding: 12px 0; font-size: 14px; }

/* ========================================================
   4. 布局结构 & 侧边栏
   ======================================================== */
.profile-shell {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 24px;
}

.profile-sidebar { padding: 0; display: flex; flex-direction: column; }
.avatar-panel {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  padding: 30px 20px 24px; border-bottom: 1px solid var(--border-main);
  background: rgba(0,0,0,0.2);
}
.avatar-image-wrap, .avatar-fallback {
  width: 80px; height: 80px;
  display: flex; align-items: center; justify-content: center;
  font-size: 32px; font-weight: bold; color: var(--accent-cyan);
  background: var(--bg-input); margin-bottom: 10px;
  text-shadow: 0 0 10px var(--accent-cyan-glow);
}
/* 工业风特有切割角效果 */
.avatar-fallback { clip-path: polygon(15px 0, 100% 0, 100% calc(100% - 15px), calc(100% - 15px) 100%, 0 100%, 0 15px); }
.avatar-image { width: 100%; height: 100%; object-fit: cover; clip-path: polygon(15px 0, 100% 0, 100% calc(100% - 15px), calc(100% - 15px) 100%, 0 100%, 0 15px); }

.operator-name { font-size: 18px; color: var(--text-bright); letter-spacing: 1px; }
.operator-id { font-size: 13px; }

.status-badge {
  display: inline-flex; align-items: center; padding: 4px 10px; font-size: 12px; font-weight: 600;
  border: 1px solid var(--accent-cyan); background: rgba(0,229,255,0.1); color: var(--accent-cyan);
  text-transform: uppercase; letter-spacing: 1px;
}

/* 导航选项卡 */
.tab-list { display: flex; flex-direction: column; padding: 12px; gap: 8px; }
.cyber-tab-btn {
  text-align: left; padding: 14px 16px; background: transparent;
  border: 1px solid transparent; border-left: 2px solid transparent;
  color: var(--text-muted); font-size: 14px; font-weight: 600; letter-spacing: 1px;
  cursor: pointer; transition: all 0.2s; font-family: inherit;
}
.cyber-tab-btn:hover { background: rgba(0,0,0,0.3); color: var(--text-main); }
.cyber-tab-btn.active {
  background: rgba(0, 229, 255, 0.05); border-color: var(--border-main);
  border-left-color: var(--accent-cyan); color: var(--accent-cyan);
  box-shadow: inset 10px 0 20px -10px var(--accent-cyan-glow);
}

/* ========================================================
   5. 表单区与输入框
   ======================================================== */
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.input-group { display: flex; flex-direction: column; gap: 8px; }
.input-group label { font-size: 12px; color: var(--text-muted); letter-spacing: 1px; }
.input-group.full-width { grid-column: 1 / -1; }

.cyber-input {
  width: 100%; padding: 10px 14px; background: var(--bg-input);
  border: 1px solid var(--border-main); color: var(--text-main);
  font-size: 14px; outline: none; transition: all 0.2s; box-sizing: border-box;
}
.cyber-input:focus { border-color: var(--accent-cyan); box-shadow: 0 0 10px rgba(0, 229, 255, 0.15); }
.cyber-input::placeholder { color: #3a5472; }

.action-row { display: flex; justify-content: flex-end; margin-top: 24px; padding-top: 20px; border-top: 1px dashed var(--border-main); }

/* 按钮样式 */
.btn {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 8px 24px; min-height: 40px; font-size: 14px; font-weight: 600; letter-spacing: 1px;
  cursor: pointer; transition: all 0.2s ease; outline: none; font-family: inherit;
}
.cyber-btn { background: transparent; border: 1px solid var(--border-light); color: var(--text-main); position: relative; overflow: hidden; }
.cyber-btn::before {
  content: ''; position: absolute; top:0; left:0; right:0; bottom:0;
  background: var(--accent-cyan); opacity: 0; transition: opacity 0.2s; z-index: -1;
}
.btn-primary { border-color: var(--accent-cyan); color: var(--accent-cyan); box-shadow: inset 0 0 8px rgba(0, 229, 255, 0.1); }
.btn-primary:hover:not(:disabled) { color: #000; box-shadow: 0 0 15px var(--accent-cyan-glow); }
.btn-primary:hover:not(:disabled)::before { opacity: 1; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; border-color: var(--border-main); color: var(--text-muted); }

/* ========================================================
   6. 权限矩阵面板 (复杂数据列)
   ======================================================== */
.permission-columns { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px; }
.cyber-sub-panel {
  background: rgba(0, 0, 0, 0.2); border: 1px solid var(--border-main);
  display: flex; flex-direction: column;
}

.col-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 16px; border-bottom: 1px solid var(--border-main);
  background: rgba(0,0,0,0.4);
}
.col-header strong { font-size: 15px; letter-spacing: 1px; }

.count-badge { padding: 2px 8px; font-size: 12px; font-family: monospace; border: 1px solid; }
.green-badge { border-color: rgba(0,255,136,0.3); color: var(--accent-green); background: rgba(0,255,136,0.05); }
.red-badge { border-color: rgba(255,51,102,0.3); color: var(--accent-red); background: rgba(255,51,102,0.05); }

.permission-list { display: flex; flex-direction: column; gap: 20px; padding: 16px; max-height: 600px; overflow-y: auto; }
.permission-group { display: flex; flex-direction: column; gap: 10px; }
.permission-group-title { padding-bottom: 6px; border-bottom: 1px dashed var(--border-light); }
.permission-group-title strong { font-size: 13px; text-transform: uppercase; letter-spacing: 1px; }

.data-box {
  background: rgba(0, 0, 0, 0.4); border: 1px solid var(--border-main);
  padding: 12px; transition: border-color 0.2s;
}
.data-box:hover { border-color: var(--border-light); }

.permission-item { display: flex; gap: 12px; align-items: flex-start; }
.cyber-icon { font-family: monospace; font-size: 14px; font-weight: bold; margin-top: 2px; }
.icon-success { color: var(--accent-green); }
.icon-danger { color: var(--accent-red); }

.item-details { display: flex; flex-direction: column; gap: 4px; }
.item-details strong { font-size: 14px; }
.item-details code { font-size: 12px; background: rgba(0,0,0,0.5); padding: 2px 6px; border: 1px solid var(--border-main); display: inline-block; width: fit-content; }
.item-details p { margin: 2px 0 0; font-size: 12px; line-height: 1.4; }

/* 自定义滚动条 */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg-app); border-left: 1px solid var(--border-main); }
::-webkit-scrollbar-thumb { background: var(--border-light); }
::-webkit-scrollbar-thumb:hover { background: var(--accent-cyan); }

/* ========================================================
   7. 响应式布局
   ======================================================== */
@media (max-width: 980px) {
  .profile-shell { grid-template-columns: 1fr; }
  .profile-sidebar { flex-direction: row; flex-wrap: wrap; align-items: center; gap: 20px; padding: 16px; }
  .avatar-panel { flex-direction: row; border-bottom: none; padding: 0; background: transparent; flex: 1; }
  .avatar-image-wrap, .avatar-fallback { width: 50px; height: 50px; font-size: 20px; margin-bottom: 0; }
  .tab-list { flex-direction: row; flex: 2; border-left: 1px dashed var(--border-main); padding-left: 20px; }
  .cyber-tab-btn { text-align: center; border-left: none; border-bottom: 2px solid transparent; }
  .cyber-tab-btn.active { border-left-color: transparent; border-bottom-color: var(--accent-cyan); box-shadow: inset 0 -10px 20px -10px var(--accent-cyan-glow); }
  .permission-columns, .form-grid { grid-template-columns: 1fr; }
}
</style>