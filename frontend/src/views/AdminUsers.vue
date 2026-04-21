<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { assignUserRoles, createUser, getMe, listRoles, listUsers, updateUser, type RoleRecord, type UserRecord } from '../api/auth'

const loading = ref(false)
const saving = ref(false)
const error = ref('')
const users = ref<UserRecord[]>([])
const roles = ref<RoleRecord[]>([])
const currentUserId = ref<number | null>(null)

const showCreateForm = ref(false)
const form = ref({
  username: '',
  display_name: '',
  email: '',
  password: '',
  roles: ['viewer'] as string[],
})

const editingUserId = ref<number | null>(null)
const editDraft = ref<Partial<UserRecord>>({})
const editPasswordDraft = ref('')

const roleOptions = computed(() => roles.value.map((item) => item.name))
const adminUsers = computed(() => users.value.filter((user) => user.roles.includes('admin')))
const soleAdminUserId = computed(() => (adminUsers.value.length === 1 ? adminUsers.value[0].id : null))
const adminExists = computed(() => adminUsers.value.length > 0)

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const [userItems, roleItems, me] = await Promise.all([listUsers(), listRoles(), getMe()])
    users.value = userItems
    roles.value = roleItems
    currentUserId.value = me.user?.id ?? null

    if (adminExists.value && !isCurrentCreateFormAdminAllowed()) {
      form.value.roles = ['viewer']
    }

    if (editingUserId.value) {
      const current = users.value.find((item) => item.id === editingUserId.value)
      if (current) {
        const currentRole = String((editDraft.value.roles ?? current.roles)[0] ?? 'viewer')
        editDraft.value.roles = [isRoleAllowedForEdit(current, currentRole) ? currentRole : current.roles[0] ?? 'viewer']
        if (!isStatusEditableForUser(current)) {
          editDraft.value.status = 'active'
        }
      }
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '用户数据加载失败'
  } finally {
    loading.value = false
  }
}

function isCurrentCreateFormAdminAllowed() {
  return !adminExists.value
}

function isRoleAllowedForEdit(user: UserRecord, role: string) {
  if (role === 'admin') {
    if (user.roles.includes('admin')) return true
    return !adminExists.value
  }
  if (user.roles.includes('admin') && soleAdminUserId.value === user.id) {
    return false
  }
  return true
}

function isRoleDisabledForCreate(role: string) {
  return role === 'admin' && adminExists.value
}

function isRoleDisabledForEdit(user: UserRecord, role: string) {
  if (role !== 'admin') {
    return user.roles.includes('admin') && soleAdminUserId.value === user.id
  }
  if (user.roles.includes('admin')) {
    return false
  }
  return adminExists.value
}

function isStatusEditableForUser(user: UserRecord) {
  return !(user.roles.includes('admin') && soleAdminUserId.value === user.id)
}

function onCreateRoleSelect(role: string) {
  form.value.roles = [role]
}

function onEditRoleSelect(role: string) {
  editDraft.value.roles = [role]
}

async function submitUser() {
  saving.value = true
  error.value = ''
  try {
    await createUser({
      username: form.value.username.trim(),
      display_name: form.value.display_name.trim(),
      email: form.value.email.trim() || null,
      password: form.value.password,
      roles: form.value.roles,
    })
    form.value = { username: '', display_name: '', email: '', password: '', roles: ['viewer'] }
    showCreateForm.value = false
    await loadAll()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '用户创建失败'
  } finally {
    saving.value = false
  }
}

function startEdit(user: UserRecord) {
  editingUserId.value = user.id
  editDraft.value = { ...user, roles: [...user.roles] }
  editPasswordDraft.value = ''
}

function cancelEdit() {
  editingUserId.value = null
  editDraft.value = {}
  editPasswordDraft.value = ''
}

async function saveEdit() {
  if (!editingUserId.value) return
  saving.value = true
  error.value = ''
  try {
    const id = editingUserId.value
    const draft = editDraft.value
    const password = editPasswordDraft.value?.trim()

    await updateUser(id, {
      display_name: draft.display_name || '',
      email: draft.email || '',
      status: draft.status || 'active',
      ...(password ? { password } : {}),
    })

    await assignUserRoles(id, (draft.roles as string[] | undefined) ?? ['viewer'])

    editingUserId.value = null
    await loadAll()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '更新失败'
  } finally {
    saving.value = false
  }
}

onMounted(loadAll)
</script>

<template>
  <section class="panel admin-users-page">
    <div class="page-heading">
      <div>
        <p class="eyebrow">Security</p>
        <h2>用户与角色</h2>
        <p>系统当前为单角色模型，每个用户只能拥有一个角色。管理员保护规则仍由后端最终校验。</p>
      </div>
      <div class="heading-actions">
        <button type="button" class="secondary-button" @click="showCreateForm = !showCreateForm">
          {{ showCreateForm ? '取消创建' : '创建用户' }}
        </button>
        <button type="button" class="secondary-button" @click="loadAll" :disabled="loading">
          {{ loading ? '刷新中...' : '刷新' }}
        </button>
      </div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="showCreateForm" class="create-section">
      <form class="config-form" @submit.prevent="submitUser">
        <h3>新增用户</h3>
        <div class="form-grid">
          <label>
            <span>用户名</span>
            <input v-model="form.username" required placeholder="登录账号" />
          </label>
          <label>
            <span>显示名</span>
            <input v-model="form.display_name" required placeholder="用户昵称" />
          </label>
          <label>
            <span>邮箱</span>
            <input v-model="form.email" type="email" placeholder="example@domain.com" />
          </label>
          <label>
            <span>初始密码</span>
            <input v-model="form.password" type="password" minlength="8" required placeholder="至少 8 位密码" />
          </label>
          <label class="full-width">
            <span>分配角色（单选）</span>
            <div class="radio-group">
              <label v-for="role in roleOptions" :key="role" class="radio-label" :class="{ disabled: isRoleDisabledForCreate(role) }">
                <input
                  type="radio"
                  name="create-role"
                  :value="role"
                  :checked="form.roles[0] === role"
                  :disabled="isRoleDisabledForCreate(role)"
                  @change="onCreateRoleSelect(role)"
                />
                {{ role }}
              </label>
            </div>
          </label>
        </div>
        <div class="form-actions">
          <button type="button" class="secondary-button" @click="showCreateForm = false">取消</button>
          <button type="submit" :disabled="saving">{{ saving ? '创建中...' : '确认创建' }}</button>
        </div>
      </form>
    </div>

    <div class="users-list">
      <div v-for="user in users" :key="user.id" class="package-row user-card">
        <template v-if="editingUserId !== user.id">
          <div class="user-card-head">
            <div class="user-info-main">
              <p class="eyebrow">{{ user.username }}</p>
              <h3>{{ user.display_name }}</h3>
              <p class="text-muted">{{ user.email || '未设置邮箱' }}</p>
            </div>
            <div class="package-meta user-badges">
              <span class="status-badge" :class="user.status">{{ user.status }}</span>
              <span class="auth-badge">{{ user.auth_source }}</span>
            </div>
          </div>
          <div class="user-card-footer">
            <div class="role-tags">
              <span class="eyebrow">角色:</span>
              <span v-for="r in user.roles" :key="r" class="role-tag">{{ r }}</span>
            </div>
            <button type="button" class="secondary-button" @click="startEdit(user)">编辑用户</button>
          </div>
        </template>

        <template v-else>
          <div class="edit-mode-container">
            <div class="edit-header">
              <h3>正在编辑: {{ user.username }}</h3>
              <span class="auth-badge">{{ user.auth_source }}</span>
            </div>
            <div class="user-grid">
              <label>
                <span>显示名</span>
                <input v-model="editDraft.display_name" required />
              </label>
              <label>
                <span>邮箱</span>
                <input v-model="editDraft.email" type="email" />
              </label>
              <label>
                <span>状态</span>
                <select v-model="editDraft.status" :disabled="!isStatusEditableForUser(user)">
                  <option value="active">Active</option>
                  <option value="disabled">Disabled</option>
                  <option value="locked">Locked</option>
                </select>
              </label>
              <label>
                <span>重置密码</span>
                <input v-model="editPasswordDraft" type="password" minlength="8" placeholder="留空则不修改" />
              </label>
            </div>
            <div class="role-edit-section">
              <span>角色分配（单选）</span>
              <div class="radio-group">
                <label v-for="role in roleOptions" :key="role" class="radio-label" :class="{ disabled: isRoleDisabledForEdit(user, role) }">
                  <input
                    type="radio"
                    :name="`role-${user.id}`"
                    :value="role"
                    :checked="(editDraft.roles?.[0] ?? '') === role"
                    :disabled="isRoleDisabledForEdit(user, role)"
                    @change="onEditRoleSelect(role)"
                  />
                  {{ role }}
                </label>
              </div>
            </div>
            <div class="edit-actions">
              <button type="button" class="secondary-button" @click="cancelEdit" :disabled="saving">取消</button>
              <button type="button" @click="saveEdit" :disabled="saving">{{ saving ? '保存中...' : '保存更改' }}</button>
            </div>
          </div>
        </template>
      </div>
    </div>
  </section>
</template>

<style scoped>
.admin-users-page { max-width: 1000px; }
.heading-actions { display: flex; gap: 12px; }
.create-section { margin-bottom: 24px; padding: 24px; background: #f9fbfb; border: 1px solid #bacac5; border-radius: 8px; }
.create-section h3 { margin-top: 0; margin-bottom: 16px; font-size: 1.1em; color: #2f403d; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.full-width { grid-column: 1 / -1; }
.form-grid label, .user-grid label { display: grid; gap: 8px; font-weight: 600; color: #2f403d; }
.form-grid input, .user-grid input, .user-grid select, .form-grid select { width: 100%; padding: 10px; border: 1px solid #bacac5; border-radius: 6px; box-sizing: border-box; }
.form-actions { display: flex; justify-content: flex-end; gap: 12px; margin-top: 20px; }
.radio-group { display: flex; gap: 16px; flex-wrap: wrap; padding: 8px 0; }
.radio-label { display: flex !important; align-items: center; gap: 6px !important; font-weight: normal !important; cursor: pointer; }
.radio-label.disabled { opacity: 0.55; cursor: not-allowed; }
.radio-label input { width: auto !important; margin: 0; }
.users-list { display: flex; flex-direction: column; gap: 16px; }
.user-card { display: flex; flex-direction: column; padding: 16px 20px; }
.user-card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.user-info-main { display: flex; flex-direction: column; gap: 4px; }
.user-info-main h3 { margin: 0; font-size: 1.2em; color: #2f403d; }
.user-info-main p { margin: 0; }
.text-muted { color: #6c7a77; font-size: 0.9em; }
.user-badges { display: flex; gap: 8px; align-items: center; }
.status-badge { padding: 4px 10px; border-radius: 20px; font-size: 0.8em; font-weight: 600; text-transform: uppercase; }
.status-badge.active { background: #d1f4e0; color: #147a42; }
.status-badge.disabled { background: #f4d1d1; color: #7a1414; }
.status-badge.locked { background: #f4e8d1; color: #7a5e14; }
.auth-badge { padding: 4px 10px; border-radius: 20px; font-size: 0.8em; background: #e0e8e6; color: #2f403d; }
.user-card-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 16px; padding-top: 16px; border-top: 1px solid #e0e8e6; }
.role-tags { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.role-tag { background: #eef2f1; border: 1px solid #d4dfdc; padding: 2px 8px; border-radius: 4px; font-size: 0.85em; color: #4a5c58; }
.edit-mode-container { display: flex; flex-direction: column; gap: 16px; }
.edit-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e0e8e6; padding-bottom: 12px; }
.edit-header h3 { margin: 0; color: #2f403d; }
.user-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.role-edit-section { display: flex; flex-direction: column; gap: 8px; font-weight: 600; color: #2f403d; margin-top: 8px; }
.edit-actions { display: flex; justify-content: flex-end; gap: 12px; margin-top: 12px; }
@media (max-width: 768px) { .form-grid, .user-grid { grid-template-columns: 1fr; } }
</style>
