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

const avatarText = computed(() => {
  const source = profileForm.value.display_name || auth.user?.username || 'U'
  return source.trim().slice(0, 1).toUpperCase()
})

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
  <section class="panel profile-page">
    <div class="page-heading">
      <div>
        <p class="eyebrow">Profile</p>
        <h2>个人中心</h2>
        <p>在这里管理个人资料、密码与角色权限视图。</p>
      </div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="success" class="success">{{ success }}</p>
    <p v-if="loading" class="muted">正在加载个人中心。</p>

    <div class="profile-shell" v-if="!loading && auth.user">
      <aside class="profile-sidebar">
        <div class="avatar-panel">
          <div v-if="profileForm.avatar_url" class="avatar-image-wrap">
            <img :src="profileForm.avatar_url" alt="avatar" class="avatar-image" />
          </div>
          <div v-else class="avatar-fallback">{{ avatarText }}</div>
          <strong>{{ auth.user.display_name }}</strong>
          <span>{{ auth.user.username }}</span>
          <span class="role-chip">{{ auth.user.roles[0] || 'viewer' }}</span>
        </div>

        <div class="tab-list">
          <button type="button" class="tab-button" :class="{ active: activeTab === 'profile' }" @click="activeTab = 'profile'">个人资料</button>
          <button type="button" class="tab-button" :class="{ active: activeTab === 'security' }" @click="activeTab = 'security'">密码安全</button>
          <button type="button" class="tab-button" :class="{ active: activeTab === 'permissions' }" @click="activeTab = 'permissions'">权限视图</button>
        </div>
      </aside>

      <div class="profile-content">
        <div v-if="activeTab === 'profile'" class="content-card">
          <h3>个人资料</h3>
          <div class="form-grid">
            <label>
              <span>显示名</span>
              <input v-model="profileForm.display_name" />
            </label>
            <label>
              <span>邮箱</span>
              <input v-model="profileForm.email" type="email" />
            </label>
            <label class="full-width">
              <span>头像链接</span>
              <input v-model="profileForm.avatar_url" placeholder="https://example.com/avatar.png" />
            </label>
          </div>
          <div class="action-row">
            <button type="button" @click="saveProfile" :disabled="saving">{{ saving ? '保存中...' : '保存资料' }}</button>
          </div>
        </div>

        <div v-else-if="activeTab === 'security'" class="content-card">
          <h3>密码安全</h3>
          <div class="form-grid">
            <label>
              <span>当前密码</span>
              <input v-model="passwordForm.current_password" type="password" />
            </label>
            <label>
              <span>新密码</span>
              <input v-model="passwordForm.new_password" type="password" minlength="8" />
            </label>
            <label class="full-width">
              <span>确认新密码</span>
              <input v-model="passwordForm.confirm_password" type="password" minlength="8" />
            </label>
          </div>
          <div class="action-row">
            <button type="button" @click="savePassword" :disabled="saving">{{ saving ? '提交中...' : '修改密码' }}</button>
          </div>
        </div>

        <div v-else class="content-card permissions-card">
          <h3>权限视图</h3>
          <div class="permission-columns">
            <section class="permission-column granted">
              <header>
                <strong>已拥有权限</strong>
                <span>{{ ownedPermissions.length }}</span>
              </header>
              <div class="permission-list">
                <div v-for="item in ownedPermissions" :key="item.code" class="permission-item">
                  <span class="permission-icon success">✔</span>
                  <div>
                    <strong>{{ item.code }}</strong>
                    <p>{{ item.description }}</p>
                  </div>
                </div>
              </div>
            </section>

            <section class="permission-column missing">
              <header>
                <strong>未拥有权限</strong>
                <span>{{ missingPermissions.length }}</span>
              </header>
              <div class="permission-list">
                <div v-for="item in missingPermissions" :key="item.code" class="permission-item">
                  <span class="permission-icon danger">✘</span>
                  <div>
                    <strong>{{ item.code }}</strong>
                    <p>{{ item.description }}</p>
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
.profile-page { max-width: 1200px; }
.success { color: #0f766e; font-weight: 600; }
.profile-shell { display: grid; grid-template-columns: 280px minmax(0, 1fr); gap: 20px; margin-top: 20px; }
.profile-sidebar, .content-card { background: #ffffff; border: 1px solid #d8e3df; border-radius: 12px; padding: 20px; }
.avatar-panel { display: grid; justify-items: center; gap: 8px; padding-bottom: 18px; border-bottom: 1px solid #e6ece9; }
.avatar-fallback, .avatar-image-wrap { width: 88px; height: 88px; border-radius: 999px; overflow: hidden; display: flex; align-items: center; justify-content: center; background: #12685f; color: #fff; font-size: 30px; font-weight: 700; }
.avatar-image { width: 100%; height: 100%; object-fit: cover; }
.role-chip { padding: 4px 10px; border: 1px solid #d8e3df; border-radius: 999px; background: #edf5f2; font-size: 12px; color: #2f403d; }
.tab-list { display: grid; gap: 10px; margin-top: 18px; }
.tab-button { justify-content: flex-start; min-height: 42px; color: #2f403d; background: #f8fbfa; border: 1px solid #d8e3df; }
.tab-button.active { color: #ffffff; background: #12685f; border-color: #12685f; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.form-grid label { display: grid; gap: 8px; color: #2f403d; font-weight: 600; }
.form-grid input { width: 100%; padding: 10px; border: 1px solid #bacac5; border-radius: 6px; }
.full-width { grid-column: 1 / -1; }
.action-row { display: flex; justify-content: flex-end; margin-top: 18px; }
.permission-columns { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
.permission-column { border: 1px solid #e6ece9; border-radius: 10px; background: #fbfdfc; overflow: hidden; }
.permission-column header { display: flex; align-items: center; justify-content: space-between; padding: 14px 16px; border-bottom: 1px solid #e6ece9; background: #f7faf9; }
.permission-list { display: grid; gap: 10px; padding: 14px; }
.permission-item { display: grid; grid-template-columns: 28px minmax(0, 1fr); gap: 10px; align-items: start; padding: 10px 12px; border: 1px solid #e6ece9; border-radius: 8px; background: #ffffff; }
.permission-item p { margin: 4px 0 0; color: #5e6f6c; font-size: 13px; }
.permission-icon { display: inline-flex; width: 24px; height: 24px; align-items: center; justify-content: center; border-radius: 999px; font-size: 12px; font-weight: 700; }
.permission-icon.success { background: #dcfce7; color: #166534; }
.permission-icon.danger { background: #fee2e2; color: #b91c1c; }
@media (max-width: 920px) {
  .profile-shell, .permission-columns, .form-grid { grid-template-columns: 1fr; }
}
</style>
