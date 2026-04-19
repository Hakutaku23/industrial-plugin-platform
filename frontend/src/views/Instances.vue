<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  listDataSources,
  listInstances,
  runInstance,
  saveInstance,
  type DataSourceRecord,
  type PluginInstanceRecord,
  type RunPluginResult,
} from '../api/packages'

const dataSources = ref<DataSourceRecord[]>([])
const instances = ref<PluginInstanceRecord[]>([])
const runResults = ref<Record<number, RunPluginResult>>({})
const loading = ref(false)
const saving = ref(false)
const runningId = ref<number | null>(null)
const error = ref('')
const form = ref({
  name: 'demo-instance',
  package_name: 'demo-python-plugin',
  version: '0.1.0',
  input_name: 'value',
  input_data_source_id: '',
  source_tag: 'demo:value',
  output_name: 'doubled',
  output_data_source_id: '',
  target_tag: 'demo:doubled',
  dry_run: true,
  writeback_enabled: false,
  configText: '{}',
})

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    dataSources.value = await listDataSources()
    instances.value = await listInstances()
    if (!form.value.input_data_source_id && dataSources.value[0]) {
      form.value.input_data_source_id = String(dataSources.value[0].id)
      form.value.output_data_source_id = String(dataSources.value[0].id)
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '实例数据加载失败'
  } finally {
    loading.value = false
  }
}

async function submit() {
  saving.value = true
  error.value = ''
  try {
    await saveInstance({
      name: form.value.name,
      package_name: form.value.package_name,
      version: form.value.version,
      input_bindings: [
        {
          input_name: form.value.input_name,
          data_source_id: Number(form.value.input_data_source_id),
          source_tag: form.value.source_tag,
        },
      ],
      output_bindings: [
        {
          output_name: form.value.output_name,
          data_source_id: Number(form.value.output_data_source_id),
          target_tag: form.value.target_tag,
          dry_run: form.value.dry_run,
        },
      ],
      config: JSON.parse(form.value.configText),
      writeback_enabled: form.value.writeback_enabled,
    })
    await loadAll()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '实例保存失败'
  } finally {
    saving.value = false
  }
}

async function run(instance: PluginInstanceRecord) {
  runningId.value = instance.id
  error.value = ''
  try {
    const result = await runInstance(instance.id)
    runResults.value = { ...runResults.value, [instance.id]: result }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '实例运行失败'
  } finally {
    runningId.value = null
  }
}

function stringify(value: unknown) {
  return JSON.stringify(value, null, 2)
}

onMounted(loadAll)
</script>

<template>
  <section class="panel">
    <div class="intro page-heading">
      <div>
        <p class="eyebrow">Instances</p>
        <h2>运行实例</h2>
        <p>绑定插件输入输出到数据源位点，然后按实例运行。</p>
      </div>
      <button type="button" class="secondary-button" @click="loadAll" :disabled="loading">
        {{ loading ? '刷新中' : '刷新' }}
      </button>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <form class="config-form" @submit.prevent="submit">
      <label>
        实例名
        <input v-model="form.name" />
      </label>
      <label>
        插件名
        <input v-model="form.package_name" />
      </label>
      <label>
        版本
        <input v-model="form.version" />
      </label>
      <label>
        输入名
        <input v-model="form.input_name" />
      </label>
      <label>
        输入数据源
        <select v-model="form.input_data_source_id">
          <option v-for="source in dataSources" :key="source.id" :value="source.id">
            {{ source.name }}
          </option>
        </select>
      </label>
      <label>
        输入位点
        <input v-model="form.source_tag" />
      </label>
      <label>
        输出名
        <input v-model="form.output_name" />
      </label>
      <label>
        输出数据源
        <select v-model="form.output_data_source_id">
          <option v-for="source in dataSources" :key="source.id" :value="source.id">
            {{ source.name }}
          </option>
        </select>
      </label>
      <label>
        输出位点
        <input v-model="form.target_tag" />
      </label>
      <label class="checkbox-line">
        <input v-model="form.dry_run" type="checkbox" />
        Dry-run 写回
      </label>
      <label class="checkbox-line">
        <input v-model="form.writeback_enabled" type="checkbox" />
        允许真实写回
      </label>
      <label class="json-input wide-field">
        实例配置 JSON
        <textarea v-model="form.configText" rows="4" spellcheck="false"></textarea>
      </label>
      <button type="submit" :disabled="saving">{{ saving ? '保存中' : '保存实例' }}</button>
    </form>

    <div v-for="instance in instances" :key="instance.id" class="package-row">
      <div class="package-main">
        <div>
          <p class="eyebrow">{{ instance.package_name }} @ {{ instance.version }}</p>
          <h3>{{ instance.name }}</h3>
          <p>{{ instance.writeback_enabled ? '允许真实写回' : '仅 dry-run / 阻断写回' }}</p>
        </div>
        <div class="package-meta">
          <span>{{ instance.status }}</span>
        </div>
      </div>
      <button type="button" class="secondary-button" @click="run(instance)" :disabled="runningId === instance.id">
        {{ runningId === instance.id ? '运行中' : '运行实例' }}
      </button>
      <pre>{{ stringify({ input_bindings: instance.input_bindings, output_bindings: instance.output_bindings }) }}</pre>
      <pre v-if="runResults[instance.id]">{{ stringify(runResults[instance.id]) }}</pre>
    </div>
  </section>
</template>
