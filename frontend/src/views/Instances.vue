<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import {
  deleteInstance,
  listDataSources,
  listInstances,
  listPackages,
  listPackageVersions,
  listRuns,
  runInstance,
  saveInstance,
  updateInstanceSchedule,
  type DataSourceRecord,
  type PluginInstanceRecord,
  type PluginPackageSummary,
  type PluginRunRecord,
  type PluginVersionRecord,
  type RunPluginResult,
} from '../api/packages'

interface InputBindingRow {
  input_name: string
  data_source_id: string
  source_tag: string
}

interface OutputBindingRow {
  output_name: string
  data_source_id: string
  target_tag: string
  dry_run: boolean
}

interface PointOption {
  label: string
  tag: string
}

const dataSources = ref<DataSourceRecord[]>([])
const pluginPackages = ref<PluginPackageSummary[]>([])
const pluginVersions = ref<PluginVersionRecord[]>([])
const instances = ref<PluginInstanceRecord[]>([])
const recentRuns = ref<PluginRunRecord[]>([])
const runResults = ref<Record<number, RunPluginResult>>({})
const loading = ref(false)
const saving = ref(false)
const runningId = ref<number | null>(null)
const operatingId = ref<number | null>(null)
const editingInstanceId = ref<number | null>(null)
const error = ref('')
const form = ref({
  name: 'demo-instance',
  package_name: '',
  version: '',
  writeback_enabled: false,
  schedule_enabled: false,
  schedule_interval_sec: 30,
  configText: '{}',
})
const inputBindings = ref<InputBindingRow[]>([])
const outputBindings = ref<OutputBindingRow[]>([])
let refreshTimer: number | undefined

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    pluginPackages.value = await listPackages()
    dataSources.value = await listDataSources()
    instances.value = await listInstances()
    recentRuns.value = await listRuns()
    await applyDefaultPlugin()
    applyDefaultDataSource()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '实例数据加载失败'
  } finally {
    loading.value = false
  }
}

async function loadPluginVersions(packageName: string) {
  pluginVersions.value = packageName ? await listPackageVersions(packageName) : []
}

async function applyDefaultPlugin() {
  const currentPackage = pluginPackages.value.find((item) => item.name === form.value.package_name)
  const selectedPackage = currentPackage ?? pluginPackages.value[0]
  if (!selectedPackage) {
    form.value.package_name = ''
    form.value.version = ''
    pluginVersions.value = []
    return
  }

  form.value.package_name = selectedPackage.name
  await loadPluginVersions(selectedPackage.name)
  const currentVersion = pluginVersions.value.find((item) => item.version === form.value.version)
  form.value.version =
    currentVersion?.version ?? selectedPackage.latest_version ?? pluginVersions.value[0]?.version ?? ''
}

async function onPackageChange() {
  await loadPluginVersions(form.value.package_name)
  form.value.version = pluginVersions.value[0]?.version ?? ''
}

function applyDefaultDataSource() {
  const defaultId = dataSources.value[0] ? String(dataSources.value[0].id) : ''
  for (const binding of inputBindings.value) {
    if (!binding.data_source_id) {
      binding.data_source_id = defaultId
    }
  }
  for (const binding of outputBindings.value) {
    if (!binding.data_source_id) {
      binding.data_source_id = defaultId
    }
  }
}

function addInputBinding() {
  inputBindings.value.push({
    input_name: '',
    data_source_id: dataSources.value[0] ? String(dataSources.value[0].id) : '',
    source_tag: '',
  })
}

function removeInputBinding(index: number) {
  inputBindings.value.splice(index, 1)
}

function addOutputBinding() {
  outputBindings.value.push({
    output_name: '',
    data_source_id: dataSources.value[0] ? String(dataSources.value[0].id) : '',
    target_tag: '',
    dry_run: true,
  })
}

function removeOutputBinding(index: number) {
  outputBindings.value.splice(index, 1)
}

async function submit() {
  saving.value = true
  error.value = ''
  try {
    if (!form.value.name.trim()) {
      throw new Error('请填写实例名')
    }
    if (!form.value.package_name || !form.value.version) {
      throw new Error('请选择插件和版本')
    }

    const normalizedInputBindings = inputBindings.value
      .filter((binding) => binding.input_name.trim() && binding.data_source_id && binding.source_tag.trim())
      .map((binding) => ({
        input_name: binding.input_name.trim(),
        data_source_id: Number(binding.data_source_id),
        source_tag: binding.source_tag.trim(),
      }))
    const normalizedOutputBindings = outputBindings.value
      .filter((binding) => binding.output_name.trim() && binding.data_source_id && binding.target_tag.trim())
      .map((binding) => ({
        output_name: binding.output_name.trim(),
        data_source_id: Number(binding.data_source_id),
        target_tag: binding.target_tag.trim(),
        dry_run: binding.dry_run,
      }))
    const duplicateInput = duplicateBindingKey(
      normalizedInputBindings.map((binding) => `${binding.data_source_id}:${binding.source_tag}`),
    )
    if (duplicateInput) {
      throw new Error(`读取绑定重复：${duplicateInput}`)
    }
    const duplicateOutput = duplicateBindingKey(
      normalizedOutputBindings.map((binding) => `${binding.data_source_id}:${binding.target_tag}`),
    )
    if (duplicateOutput) {
      throw new Error(`回写绑定重复：${duplicateOutput}`)
    }

    await saveInstance({
      id: editingInstanceId.value,
      name: form.value.name.trim(),
      package_name: form.value.package_name,
      version: form.value.version,
      input_bindings: normalizedInputBindings,
      output_bindings: normalizedOutputBindings,
      config: JSON.parse(form.value.configText),
      writeback_enabled: form.value.writeback_enabled,
      schedule_enabled: form.value.schedule_enabled,
      schedule_interval_sec: Number(form.value.schedule_interval_sec) || 30,
    })
    await loadAll()
    resetForm()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '实例保存失败'
  } finally {
    saving.value = false
  }
}

function duplicateBindingKey(keys: string[]) {
  const seen = new Set<string>()
  for (const key of keys) {
    if (seen.has(key)) {
      return key
    }
    seen.add(key)
  }
  return ''
}

async function run(instance: PluginInstanceRecord) {
  runningId.value = instance.id
  error.value = ''
  try {
    const result = await runInstance(instance.id)
    runResults.value = { ...runResults.value, [instance.id]: result }
    recentRuns.value = await listRuns()
    await loadAll()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '实例运行失败'
  } finally {
    runningId.value = null
  }
}

async function stopSchedule(instance: PluginInstanceRecord) {
  operatingId.value = instance.id
  error.value = ''
  try {
    await updateInstanceSchedule(instance.id, { enabled: false })
    await loadAll()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '实例停止失败'
  } finally {
    operatingId.value = null
  }
}

async function startSchedule(instance: PluginInstanceRecord) {
  operatingId.value = instance.id
  error.value = ''
  try {
    await updateInstanceSchedule(instance.id, {
      enabled: true,
      interval_sec: instance.schedule_interval_sec || 30,
    })
    await loadAll()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '实例定时启动失败'
  } finally {
    operatingId.value = null
  }
}

async function removeInstance(instance: PluginInstanceRecord) {
  if (!window.confirm(`确认删除实例 ${instance.name}？`)) {
    return
  }
  operatingId.value = instance.id
  error.value = ''
  try {
    await deleteInstance(instance.id)
    if (editingInstanceId.value === instance.id) {
      resetForm()
    }
    await loadAll()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '实例删除失败'
  } finally {
    operatingId.value = null
  }
}

async function editInstance(instance: PluginInstanceRecord) {
  editingInstanceId.value = instance.id
  form.value = {
    name: instance.name,
    package_name: instance.package_name,
    version: instance.version,
    writeback_enabled: instance.writeback_enabled,
    schedule_enabled: instance.schedule_enabled,
    schedule_interval_sec: instance.schedule_interval_sec || 30,
    configText: JSON.stringify(instance.config ?? {}, null, 2),
  }
  await loadPluginVersions(instance.package_name)
  inputBindings.value = instance.input_bindings.map((binding) => ({
    input_name: stringValue(binding.input_name),
    data_source_id: stringValue(binding.data_source_id),
    source_tag: stringValue(binding.source_tag),
  }))
  outputBindings.value = instance.output_bindings.map((binding) => ({
    output_name: stringValue(binding.output_name),
    data_source_id: stringValue(binding.data_source_id),
    target_tag: stringValue(binding.target_tag),
    dry_run: Boolean(binding.dry_run ?? true),
  }))
}

function resetForm() {
  editingInstanceId.value = null
  form.value = {
    name: 'demo-instance',
    package_name: pluginPackages.value[0]?.name ?? '',
    version: pluginPackages.value[0]?.latest_version ?? '',
    writeback_enabled: false,
    schedule_enabled: false,
    schedule_interval_sec: 30,
    configText: '{}',
  }
  inputBindings.value = []
  outputBindings.value = []
}

function inputOptions(binding: InputBindingRow, index: number) {
  const source = findDataSource(binding.data_source_id)
  if (!source) {
    return []
  }
  return getReadPointOptions(source).filter(
    (point) => !isInputTagSelectedByOtherRow(index, binding.data_source_id, point.tag),
  )
}

function outputOptions(binding: OutputBindingRow, index: number) {
  const source = findDataSource(binding.data_source_id)
  if (!source) {
    return []
  }
  return getWritePointOptions(source).filter(
    (point) => !isOutputTagSelectedByOtherRow(index, binding.data_source_id, point.tag),
  )
}

function isInputTagSelectedByOtherRow(index: number, dataSourceId: string, tag: string) {
  return inputBindings.value.some(
    (binding, bindingIndex) =>
      bindingIndex !== index && binding.data_source_id === dataSourceId && binding.source_tag === tag,
  )
}

function isOutputTagSelectedByOtherRow(index: number, dataSourceId: string, tag: string) {
  return outputBindings.value.some(
    (binding, bindingIndex) =>
      bindingIndex !== index && binding.data_source_id === dataSourceId && binding.target_tag === tag,
  )
}

function findDataSource(dataSourceId: string) {
  return dataSources.value.find((item) => String(item.id) === String(dataSourceId))
}

function stringify(value: unknown) {
  return JSON.stringify(value, null, 2)
}

function formatTime(value: string | null) {
  if (!value) {
    return '未计划'
  }
  return new Date(value).toLocaleString()
}

function recentRunsForInstance(instance: PluginInstanceRecord) {
  return recentRuns.value
    .filter((run) => {
      if (run.instance_id === instance.id) {
        return true
      }
      return (
        run.instance_id === null &&
        run.package_name === instance.package_name &&
        run.version === instance.version
      )
    })
    .slice(0, 3)
}

function getReadPointOptions(source: DataSourceRecord) {
  const catalog = catalogFromConfig(source)
  if (Array.isArray(catalog)) {
    const points = catalog
      .map((point) => pointOption(point, ['readTag', 'read_tag'], ['canRead', 'can_read']))
      .filter((point): point is PointOption => Boolean(point))
    if (points.length > 0) {
      return points
    }
  }
  const configured = tagListFromConfig(source, 'readTags', 'read_tags')
  if (configured.length > 0) {
    return configured.map((tag) => ({ label: tag, tag }))
  }
  if (source.connector_type === 'mock' && isRecord(source.config.points)) {
    return Object.keys(source.config.points).map((tag) => ({ label: tag, tag }))
  }
  return []
}

function getWritePointOptions(source: DataSourceRecord) {
  const catalog = catalogFromConfig(source)
  if (Array.isArray(catalog)) {
    const points = catalog
      .map((point) => pointOption(point, ['writeTag', 'write_tag'], ['canWrite', 'can_write']))
      .filter((point): point is PointOption => Boolean(point))
    if (points.length > 0) {
      return points
    }
  }
  const configured = tagListFromConfig(source, 'writeTags', 'write_tags')
  if (configured.length > 0) {
    return configured.map((tag) => ({ label: tag, tag }))
  }
  if (source.connector_type === 'mock' && isRecord(source.config.points)) {
    return Object.keys(source.config.points).map((tag) => ({ label: tag, tag }))
  }
  return []
}

function catalogFromConfig(source: DataSourceRecord) {
  return source.config.pointCatalog ?? source.config.point_catalog
}

function tagListFromConfig(
  source: DataSourceRecord,
  camelKey: 'readTags' | 'writeTags',
  snakeKey: 'read_tags' | 'write_tags',
) {
  const camel = arrayOfStrings(source.config[camelKey])
  return camel.length > 0 ? camel : arrayOfStrings(source.config[snakeKey])
}

function pointOption(
  point: unknown,
  tagFields: Array<'readTag' | 'writeTag' | 'read_tag' | 'write_tag'>,
  permissionFields: Array<'canRead' | 'canWrite' | 'can_read' | 'can_write'>,
) {
  if (!isRecord(point) || !isAllowed(point, permissionFields)) {
    return null
  }

  const tag = tagFields
    .map((field) => point[field])
    .find((value): value is string => typeof value === 'string' && value.length > 0)
  if (!tag) {
    return null
  }

  const pointClass = stringField(point, ['class', 'pointClass', 'point_class']) || '未分类'
  return {
    label: `${pointClass} / ${tag}`,
    tag,
  }
}

function isAllowed(record: Record<string, unknown>, fields: string[]) {
  const configured = fields
    .map((field) => record[field])
    .find((value): value is boolean => typeof value === 'boolean')
  return configured ?? true
}

function stringField(record: Record<string, unknown>, fields: string[]) {
  return fields
    .map((field) => record[field])
    .find((value): value is string => typeof value === 'string' && value.length > 0)
}

function stringValue(value: unknown) {
  if (value === null || value === undefined) {
    return ''
  }
  return String(value)
}

function arrayOfStrings(value: unknown) {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

onMounted(() => {
  loadAll()
  refreshTimer = window.setInterval(() => {
    loadAll()
  }, 5000)
})

onUnmounted(() => {
  if (refreshTimer !== undefined) {
    window.clearInterval(refreshTimer)
  }
})
</script>

<template>
  <section class="panel">
    <div class="intro page-heading">
      <div>
        <p class="eyebrow">Instances</p>
        <h2>运行实例</h2>
        <p>为插件配置读取、回写和定时执行。实例只保存平台侧绑定关系，插件仍由隔离 runner 执行。</p>
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
        <select v-model="form.package_name" @change="onPackageChange">
          <option value="">请先上传插件包</option>
          <option v-for="plugin in pluginPackages" :key="plugin.id" :value="plugin.name">
            {{ plugin.display_name || plugin.name }} ({{ plugin.name }})
          </option>
        </select>
      </label>
      <label>
        版本
        <select v-model="form.version" :disabled="pluginVersions.length === 0">
          <option value="">请选择版本</option>
          <option v-for="version in pluginVersions" :key="version.id" :value="version.version">
            {{ version.version }}
          </option>
        </select>
      </label>
      <label>
        定时间隔（秒）
        <input v-model.number="form.schedule_interval_sec" type="number" min="5" step="1" />
      </label>
      <label class="checkbox-line">
        <input v-model="form.schedule_enabled" type="checkbox" />
        启用定时运行
      </label>
      <label class="checkbox-line">
        <input v-model="form.writeback_enabled" type="checkbox" />
        允许真实回写
      </label>

      <div class="wide-field binding-list">
        <div class="section-title">
          <strong>读取绑定</strong>
          <button type="button" class="secondary-button" @click="addInputBinding">新增读取</button>
        </div>
        <div class="binding-table">
          <div class="binding-table-head binding-row">
            <span>插件输入名</span>
            <span>数据源</span>
            <span>读取位点</span>
            <span>手动 Redis Key</span>
            <span>操作</span>
          </div>
          <div v-for="(binding, index) in inputBindings" :key="index" class="binding-row">
            <input v-model="binding.input_name" aria-label="插件输入名" placeholder="如 value、temperature" />
            <select v-model="binding.data_source_id" aria-label="读取数据源" @change="binding.source_tag = ''">
              <option value="">请选择数据源</option>
              <option v-for="source in dataSources" :key="source.id" :value="source.id">
                {{ source.name }}
              </option>
            </select>
            <select v-model="binding.source_tag" aria-label="读取位点">
              <option value="">请选择可读位点</option>
              <option v-for="point in inputOptions(binding, index)" :key="point.tag" :value="point.tag">
                {{ point.label }}
              </option>
            </select>
            <input v-model="binding.source_tag" aria-label="手动读取 Redis Key" placeholder="如 sthb:DCS_AO_RTO_014_AI" />
            <button type="button" class="danger-button" @click="removeInputBinding(index)">删除</button>
          </div>
        </div>
      </div>

      <div class="wide-field binding-list">
        <div class="section-title">
          <strong>回写绑定</strong>
          <button type="button" class="secondary-button" @click="addOutputBinding">新增回写</button>
        </div>
        <div class="binding-table">
          <div class="binding-table-head binding-row binding-row-output">
            <span>插件输出名</span>
            <span>数据源</span>
            <span>回写位点</span>
            <span>手动 Redis Key</span>
            <span>Dry-run</span>
            <span>操作</span>
          </div>
          <div v-for="(binding, index) in outputBindings" :key="index" class="binding-row binding-row-output">
            <input v-model="binding.output_name" aria-label="插件输出名" placeholder="如 doubled、setpoint" />
            <select v-model="binding.data_source_id" aria-label="回写数据源" @change="binding.target_tag = ''">
              <option value="">请选择数据源</option>
              <option v-for="source in dataSources" :key="source.id" :value="source.id">
                {{ source.name }}
              </option>
            </select>
            <select v-model="binding.target_tag" aria-label="回写位点">
              <option value="">请选择可写位点</option>
              <option v-for="point in outputOptions(binding, index)" :key="point.tag" :value="point.tag">
                {{ point.label }}
              </option>
            </select>
            <input v-model="binding.target_tag" aria-label="手动回写 Redis Key" placeholder="如 sthb:DCS_AO_RTO_014_AO" />
            <label class="inline-check">
              <input v-model="binding.dry_run" type="checkbox" />
              Dry-run
            </label>
            <button type="button" class="danger-button" @click="removeOutputBinding(index)">删除</button>
          </div>
        </div>
      </div>

      <label class="json-input wide-field">
        实例配置 JSON
        <textarea v-model="form.configText" rows="4" spellcheck="false"></textarea>
      </label>
      <div class="form-actions wide-field">
        <button type="submit" :disabled="saving">{{ saving ? '保存中' : editingInstanceId ? '保存修改' : '保存实例' }}</button>
        <button v-if="editingInstanceId" type="button" class="secondary-button" @click="resetForm">取消编辑</button>
      </div>
    </form>

    <div v-for="instance in instances" :key="instance.id" class="package-row">
      <div class="package-main">
        <div>
          <p class="eyebrow">{{ instance.package_name }} @ {{ instance.version }}</p>
          <h3>{{ instance.name }}</h3>
          <p>{{ instance.writeback_enabled ? '允许真实回写' : '仅 dry-run / 阻断真实回写' }}</p>
        </div>
        <div class="package-meta">
          <span>{{ instance.status }}</span>
          <span>{{ instance.schedule_enabled ? `每 ${instance.schedule_interval_sec} 秒` : '未启用定时' }}</span>
        </div>
      </div>

      <div class="status-grid">
        <div>
          <span>上次定时</span>
          <strong>{{ formatTime(instance.last_scheduled_run_at) }}</strong>
        </div>
        <div>
          <span>下次定时</span>
          <strong>{{ formatTime(instance.next_scheduled_run_at) }}</strong>
        </div>
      </div>

      <div class="instance-actions">
        <button type="button" class="secondary-button" @click="editInstance(instance)">修改</button>
        <button type="button" class="secondary-button" @click="run(instance)" :disabled="runningId === instance.id">
          {{ runningId === instance.id ? '运行中' : '手动运行' }}
        </button>
        <button
          v-if="instance.schedule_enabled"
          type="button"
          class="secondary-button"
          @click="stopSchedule(instance)"
          :disabled="operatingId === instance.id"
        >
          停止定时
        </button>
        <button
          v-else
          type="button"
          class="secondary-button"
          @click="startSchedule(instance)"
          :disabled="operatingId === instance.id"
        >
          启动定时
        </button>
        <button
          type="button"
          class="danger-button"
          @click="removeInstance(instance)"
          :disabled="operatingId === instance.id"
        >
          删除实例
        </button>
      </div>

      <pre>{{ stringify({ input_bindings: instance.input_bindings, output_bindings: instance.output_bindings }) }}</pre>
      <div class="run-history">
        <strong>最近运行</strong>
        <div v-if="recentRunsForInstance(instance).length === 0" class="muted">
          暂无运行记录，定时触发后这里会自动刷新。
        </div>
        <div v-for="run in recentRunsForInstance(instance)" :key="run.run_id" class="run-history-row">
          <span>{{ run.trigger_type }}</span>
          <span>{{ run.status }}</span>
          <span>{{ formatTime(run.finished_at) }}</span>
          <code>{{ run.run_id }}</code>
        </div>
      </div>
      <pre v-if="runResults[instance.id]">{{ stringify(runResults[instance.id]) }}</pre>
    </div>
  </section>
</template>
