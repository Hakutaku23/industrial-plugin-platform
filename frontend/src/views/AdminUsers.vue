<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { assignUserRoles, createUser, listRoles, listUsers, updateUser, type RoleRecord, type UserRecord } from '../api/auth'

const loading = ref(false)
const saving = ref(false)
const error = ref('')
const users = ref<UserRecord[]>([])
const roles = ref<RoleRecord[]>([])
const form = ref({
  username: '',
  display_name: '',
  email: '',
  password: '',
  roles: ['viewer'] as string[],
})
const passwordDrafts = ref<Record<number, string>>({})

const roleOptions = computed(() => roles.value.map((item) => item.name))

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    ;[users.value, roles.value] = await Promise.all([listUsers(), listRoles()])
  } catch (err) {
    error.value = err instanceof Error ? err.message : '用户数据加载失败'
  } finally {
    loading.value = false
  }
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
    await loadAll()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '用户创建失败'
  } finally {
    saving.value = false
  }
}

async function saveRoles(user: UserRecord) {
  try {
    await assignUserRoles(user.id, user.roles)
    await loadAll()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '角色更新失败'
  }
}

async function saveProfile(user: UserRecord) {
  try {
    const password = passwordDrafts.value[user.id]?.trim()
    await updateUser(user.id, {
      display_name: user.display_name,
      email: user.email || '',
      status: user.status,
      ...(password ? { password } : {}),
    })
    passwordDrafts.value[user.id] = ''
    await loadAll()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '用户更新失败'
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
        <p>Admin 可在这里创建本地用户、分配角色，并控制账号状态。</p>
      </div>
      <button type="button" class="secondary-button" @click="loadAll" :disabled="loading">
        {{ loading ? '刷新中' : '刷新' }}
      </button>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <form class="config-form create-user-form" @submit.prevent="submitUser">
      <label>
        <span>用户名</span>
        <input v-model="form.username" required />
      </label>
      <label>
        <span>显示名</span>
        <input v-model="form.display_name" required />
      </label>
      <label>
        <span>邮箱</span>
        <input v-model="form.email" />
      </label>
      <label>
        <span>初始密码</span>
        <input v-model="form.password" type="password" minlength="8" required />
      </label>
      <label>
        <span>角色</span>
        <select v-model="form.roles" multiple size="4">
          <option v-for="role in roleOptions" :key="role" :value="role">{{ role }}</option>
        </select>
      </label>
      <div class="form-actions wide-field">
        <button type="submit" :disabled="saving">{{ saving ? '创建中' : '创建用户' }}</button>
      </div>
    </form>

    <div v-for="user in users" :key="user.id" class="package-row user-card">
      <div class="user-card-head">
        <div>
          <p class="eyebrow">{{ user.username }}</p>
          <h3>{{ user.display_name }}</h3>
          <p>{{ user.email || '未设置邮箱' }}</p>
        </div>
        <div class="package-meta">
          <span>{{ user.status }}</span>
          <span>{{ user.auth_source }}</span>
        </div>
      </div>

      <div class="user-grid">
        <label>
          <span>显示名</span>
          <input v-model="user.display_name" />
        </label>
        <label>
          <span>邮箱</span>
          <input v-model="user.email" />
        </label>
        <label>
          <span>状态</span>
          <select v-model="user.status">
            <option value="active">active</option>
            <option value="disabled">disabled</option>
            <option value="locked">locked</option>
          </select>
        </label>
        <label>
          <span>重置密码</span>
          <input v-model="passwordDrafts[user.id]" type="password" minlength="8" placeholder="留空则不修改" />
        </label>
      </div>

      <label class="role-multi-select">
        <span>角色分配</span>
        <select v-model="user.roles" multiple size="5">
          <option v-for="role in roleOptions" :key="role" :value="role">{{ role }}</option>
        </select>
      </label>

      <div class="user-actions">
        <button type="button" class="secondary-button" @click="saveProfile(user)">保存资料</button>
        <button type="button" class="secondary-button" @click="saveRoles(user)">保存角色</button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.admin-users-page { max-width: 1320px; }
.create-user-form { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.user-card { display: grid; gap: 14px; }
.user-card-head, .user-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.user-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.user-grid label, .role-multi-select { display: grid; gap: 8px; font-weight: 600; color: #2f403d; }
.user-grid input, .user-grid select, .role-multi-select select { width: 100%; padding: 10px; border: 1px solid #bacac5; border-radius: 6px; box-sizing: border-box; }
@media (max-width: 980px) { .create-user-form, .user-grid { grid-template-columns: 1fr; } }
</style>
