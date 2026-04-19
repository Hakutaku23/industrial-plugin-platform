<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listDataSources, saveDataSource, type DataSourceRecord } from '../api/packages'

const dataSources = ref<DataSourceRecord[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const form = ref({
  name: 'mock-line-a',
  connector_type: 'mock' as 'mock' | 'redis',
  configText: JSON.stringify({ points: { 'demo:value': 21 } }, null, 2),
  read_enabled: true,
  write_enabled: true,
})

async function loadDataSources() {
  loading.value = true
  error.value = ''
  try {
    dataSources.value = await listDataSources()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '数据源列表加载失败'
  } finally {
    loading.value = false
  }
}

function useTemplate(type: 'mock' | 'redis') {
  form.value.connector_type = type
  form.value.configText =
    type === 'mock'
      ? JSON.stringify({ points: { 'demo:value': 21 } }, null, 2)
      : JSON.stringify(
          {
            host: '127.0.0.1',
            port: 6379,
            db: 0,
            keyPrefix: '',
          },
          null,
          2,
        )
}

async function submit() {
  saving.value = true
  error.value = ''
  try {
    await saveDataSource({
      name: form.value.name,
      connector_type: form.value.connector_type,
      config: JSON.parse(form.value.configText),
      read_enabled: form.value.read_enabled,
      write_enabled: form.value.write_enabled,
    })
    await loadDataSources()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '数据源保存失败'
  } finally {
    saving.value = false
  }
}

function stringify(value: unknown) {
  return JSON.stringify(value, null, 2)
}

onMounted(loadDataSources)
</script>

<template>
  <section class="panel">
    <div class="intro page-heading">
      <div>
        <p class="eyebrow">Connectors</p>
        <h2>数据源与位点</h2>
        <p>配置 Mock 或 Redis 数据源，用于插件输入读取和输出写回。</p>
      </div>
      <button type="button" class="secondary-button" @click="loadDataSources" :disabled="loading">
        {{ loading ? '刷新中' : '刷新' }}
      </button>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <form class="config-form" @submit.prevent="submit">
      <label>
        名称
        <input v-model="form.name" />
      </label>
      <label>
        类型
        <select v-model="form.connector_type" @change="useTemplate(form.connector_type)">
          <option value="mock">Mock</option>
          <option value="redis">Redis</option>
        </select>
      </label>
      <label class="checkbox-line">
        <input v-model="form.read_enabled" type="checkbox" />
        可读取
      </label>
      <label class="checkbox-line">
        <input v-model="form.write_enabled" type="checkbox" />
        可写回
      </label>
      <label class="json-input wide-field">
        配置 JSON
        <textarea v-model="form.configText" rows="8" spellcheck="false"></textarea>
      </label>
      <button type="submit" :disabled="saving">{{ saving ? '保存中' : '保存数据源' }}</button>
    </form>

    <div v-for="source in dataSources" :key="source.id" class="package-row">
      <div class="package-main">
        <div>
          <p class="eyebrow">{{ source.connector_type }}</p>
          <h3>{{ source.name }}</h3>
          <p>{{ source.read_enabled ? '可读取' : '不可读取' }} · {{ source.write_enabled ? '可写回' : '不可写回' }}</p>
        </div>
        <div class="package-meta">
          <span>{{ source.status }}</span>
        </div>
      </div>
      <pre>{{ stringify(source.config) }}</pre>
    </div>
  </section>
</template>
