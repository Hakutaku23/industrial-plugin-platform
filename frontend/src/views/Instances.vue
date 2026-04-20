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

type BindingType = 'single' | 'batch'
type BatchOutputFormat = 'named-map' | 'ordered-list'

interface SourceMappingRow {
  tag: string
  key: string
}

interface InputBindingRow {
  binding_type: BindingType
  input_name: string
  data_source_id: string
  source_tag: string
  source_tags: string[]
  source_mappings: SourceMappingRow[]
  output_format: BatchOutputFormat
}

interface OutputBindingRow {
  binding_type: BindingType
  output_name: string
  data_source_id: string
  target_tag: string
  target_tags: string[]
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
    if (!binding.data_source_id) binding.data_source_id = defaultId
  }
  for (const binding of outputBindings.value) {
    if (!binding.data_source_id) binding.data_source_id = defaultId
  }
}

function defaultInputBinding(): InputBindingRow {
  return {
    binding_type: 'single',
    input_name: '',
    data_source_id: dataSources.value[0] ? String(dataSources.value[0].id) : '',
    source_tag: '',
    source_tags: [],
    source_mappings: [],
    output_format: 'named-map',
  }
}

function defaultOutputBinding(): OutputBindingRow {
  return {
    binding_type: 'single',
    output_name: '',
    data_source_id: dataSources.value[0] ? String(dataSources.value[0].id) : '',
    target_tag: '',
    target_tags: [],
    dry_run: true,
  }
}

function addInputBinding() {
  inputBindings.value.push(defaultInputBinding())
}

function removeInputBinding(index: number) {
  inputBindings.value.splice(index, 1)
}

function addOutputBinding() {
  outputBindings.value.push(defaultOutputBinding())
}

function removeOutputBinding(index: number) {
  outputBindings.value.splice(index, 1)
}

function switchInputBindingType(binding: InputBindingRow, type: BindingType) {
  binding.binding_type = type
  binding.source_tag = ''
  binding.source_tags = []
  binding.source_mappings = []
}

function switchOutputBindingType(binding: OutputBindingRow, type: BindingType) {
  binding.binding_type = type
  binding.target_tag = ''
  binding.target_tags = []
}

function inputOptions(binding: InputBindingRow) {
  const source = findDataSource(binding.data_source_id)
  return source ? getReadPointOptions(source) : []
}

function outputOptions(binding: OutputBindingRow) {
  const source = findDataSource(binding.data_source_id)
  return source ? getWritePointOptions(source) : []
}

function sanitizePointKey(tag: string) {
  return tag.trim().replace(/[^A-Za-z0-9_]/g, '_')
}

function syncSourceMappings(binding: InputBindingRow) {
  const selected = Array.from(new Set(binding.source_tags.map((tag) => tag.trim()).filter(Boolean)))
  const previous = new Map(binding.source_mappings.map((item) => [item.tag, item.key]))
  binding.source_mappings = selected.map((tag) => ({
    tag,
    key: previous.get(tag) || sanitizePointKey(tag),
  }))
  binding.source_tags = selected
}

function updateInputTagSelection(binding: InputBindingRow, tag: string, checked: boolean) {
  const next = new Set(binding.source_tags)
  if (checked) next.add(tag)
  else next.delete(tag)
  binding.source_tags = Array.from(next)
  syncSourceMappings(binding)
}

function selectAllInputTags(binding: InputBindingRow) {
  binding.source_tags = inputOptions(binding).map((point) => point.tag)
  syncSourceMappings(binding)
}

function clearAllInputTags(binding: InputBindingRow) {
  binding.source_tags = []
  binding.source_mappings = []
}

function moveInputTag(binding: InputBindingRow, index: number, direction: -1 | 1) {
  const target = index + direction
  if (target < 0 || target >= binding.source_tags.length) return
  const swapped = [...binding.source_tags]
  ;[swapped[index], swapped[target]] = [swapped[target], swapped[index]]
  binding.source_tags = swapped
  syncSourceMappings(binding)
}

function updateMappingKey(binding: InputBindingRow, tag: string, value: string) {
  const next = value.trim()
  const duplicate = binding.source_mappings.some((item) => item.tag !== tag && item.key === next)
  binding.source_mappings = binding.source_mappings.map((item) =>
    item.tag === tag ? { ...item, key: duplicate ? item.key : next } : item,
  )
}

function selectAllOutputTags(binding: OutputBindingRow) {
  binding.target_tags = outputOptions(binding).map((point) => point.tag)
}

function clearAllOutputTags(binding: OutputBindingRow) {
  binding.target_tags = []
}

async function submit() {
  saving.value = true
  error.value = ''
  try {
    if (!form.value.name.trim()) throw new Error('请填写实例名')
    if (!form.value.package_name || !form.value.version) throw new Error('请选择插件和版本')

    const normalizedInputBindings = inputBindings.value
      .filter((binding) => binding.input_name.trim() && binding.data_source_id)
      .map((binding) => {
        if (binding.binding_type === 'batch') {
          const source_tags = Array.from(new Set(binding.source_tags.map((tag) => tag.trim()).filter(Boolean)))
          if (source_tags.length === 0) throw new Error(`批量读取绑定 ${binding.input_name} 未选择任何位点`)
          if (binding.output_format === 'named-map') {
            const source_mappings = binding.source_mappings
              .map((item) => ({ tag: item.tag.trim(), key: item.key.trim() }))
              .filter((item) => item.tag && item.key)
            if (source_mappings.length !== source_tags.length) {
              throw new Error(`批量读取绑定 ${binding.input_name} 存在未完成的 named-map 映射`)
            }
            const keys = source_mappings.map((item) => item.key)
            if (new Set(keys).size !== keys.length) {
              throw new Error(`批量读取绑定 ${binding.input_name} 的 named-map 键名重复`)
            }
            return {
              binding_type: 'batch' as const,
              input_name: binding.input_name.trim(),
              data_source_id: Number(binding.data_source_id),
              source_tags,
              source_mappings,
              output_format: 'named-map' as const,
            }
          }
          return {
            binding_type: 'batch' as const,
            input_name: binding.input_name.trim(),
            data_source_id: Number(binding.data_source_id),
            source_tags,
            output_format: 'ordered-list' as const,
          }
        }
        if (!binding.source_tag.trim()) throw new Error(`读取绑定 ${binding.input_name} 未选择位点`)
        return {
          binding_type: 'single' as const,
          input_name: binding.input_name.trim(),
          data_source_id: Number(binding.data_source_id),
          source_tag: binding.source_tag.trim(),
        }
      })

    const normalizedOutputBindings = outputBindings.value
      .filter((binding) => binding.output_name.trim() && binding.data_source_id)
      .map((binding) => {
        if (binding.binding_type === 'batch') {
          const target_tags = Array.from(new Set(binding.target_tags.map((tag) => tag.trim()).filter(Boolean)))
          if (target_tags.length === 0) throw new Error(`批量回写绑定 ${binding.output_name} 未选择任何位点`)
          return {
            binding_type: 'batch' as const,
            output_name: binding.output_name.trim(),
            data_source_id: Number(binding.data_source_id),
            target_tags,
            dry_run: binding.dry_run,
          }
        }
        if (!binding.target_tag.trim()) throw new Error(`回写绑定 ${binding.output_name} 未选择位点`)
        return {
          binding_type: 'single' as const,
          output_name: binding.output_name.trim(),
          data_source_id: Number(binding.data_source_id),
          target_tag: binding.target_tag.trim(),
          dry_run: binding.dry_run,
        }
      })

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
  if (!window.confirm(`确认删除实例 ${instance.name}？`)) return
  operatingId.value = instance.id
  error.value = ''
  try {
    await deleteInstance(instance.id)
    if (editingInstanceId.value === instance.id) resetForm()
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
  inputBindings.value = instance.input_bindings.map((binding) => {
    const record = binding as unknown as Record<string, unknown>
    const source_tags = arrayOfStrings(record.source_tags)
    const source_mappings = normalizeSourceMappings(record.source_mappings, source_tags)
    return {
      binding_type: normalizeBindingType(record.binding_type),
      input_name: stringValue(record.input_name),
      data_source_id: stringValue(record.data_source_id),
      source_tag: stringValue(record.source_tag),
      source_tags,
      source_mappings,
      output_format: normalizeOutputFormat(record.output_format),
    }
  })
  outputBindings.value = instance.output_bindings.map((binding) => {
    const record = binding as unknown as Record<string, unknown>
    return {
      binding_type: normalizeBindingType(record.binding_type),
      output_name: stringValue(record.output_name),
      data_source_id: stringValue(record.data_source_id),
      target_tag: stringValue(record.target_tag),
      target_tags: arrayOfStrings(record.target_tags),
      dry_run: Boolean(record.dry_run ?? true),
    }
  })
}

function normalizeSourceMappings(value: unknown, sourceTags: string[]) {
  const mappings = Array.isArray(value)
    ? value
        .filter((item): item is Record<string, unknown> => isRecord(item))
        .map((item) => ({ tag: stringValue(item.tag), key: stringValue(item.key) }))
        .filter((item) => item.tag && item.key)
    : []
  return mappings.length > 0 ? mappings : sourceTags.map((tag) => ({ tag, key: sanitizePointKey(tag) }))
}

function normalizeBindingType(value: unknown): BindingType {
  return value === 'batch' ? 'batch' : 'single'
}

function normalizeOutputFormat(value: unknown): BatchOutputFormat {
  return value === 'ordered-list' ? 'ordered-list' : 'named-map'
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

function findDataSource(dataSourceId: string) {
  return dataSources.value.find((item) => String(item.id) === String(dataSourceId))
}

function stringify(value: unknown) {
  return JSON.stringify(value, null, 2)
}

function formatTime(value: string | null) {
  if (!value) return '未计划'
  return new Date(value).toLocaleString()
}

function recentRunsForInstance(instance: PluginInstanceRecord) {
  return recentRuns.value
    .filter((run) => {
      if (run.instance_id === instance.id) return true
      return run.instance_id === null && run.package_name === instance.package_name && run.version === instance.version
    })
    .slice(0, 3)
}

function getReadPointOptions(source: DataSourceRecord) {
  const catalog = catalogFromConfig(source)
  if (Array.isArray(catalog)) {
    const points = catalog
      .map((point) => pointOption(point, ['readTag', 'read_tag'], ['canRead', 'can_read']))
      .filter((point): point is PointOption => Boolean(point))
    if (points.length > 0) return points
  }
  const configured = tagListFromConfig(source, 'readTags', 'read_tags')
  if (configured.length > 0) return configured.map((tag) => ({ label: tag, tag }))
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
    if (points.length > 0) return points
  }
  const configured = tagListFromConfig(source, 'writeTags', 'write_tags')
  if (configured.length > 0) return configured.map((tag) => ({ label: tag, tag }))
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
  if (!isRecord(point) || !isAllowed(point, permissionFields)) return null
  const tag = tagFields
    .map((field) => point[field])
    .find((value): value is string => typeof value === 'string' && value.length > 0)
  if (!tag) return null
  const pointClass = stringField(point, ['class', 'pointClass', 'point_class']) || '未分类'
  return { label: `${pointClass} / ${tag}`, tag }
}

function isAllowed(record: Record<string, unknown>, fields: string[]) {
  const configured = fields.map((field) => record[field]).find((value): value is boolean => typeof value === 'boolean')
  return configured ?? true
}

function stringField(record: Record<string, unknown>, fields: string[]) {
  return fields.map((field) => record[field]).find((value): value is string => typeof value === 'string' && value.length > 0)
}

function stringValue(value: unknown) {
  if (value === null || value === undefined) return ''
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
  if (refreshTimer !== undefined) window.clearInterval(refreshTimer)
})
</script>

<template>
  <section class="panel instances-page">
    <div class="intro page-heading">
      <div>
        <p class="eyebrow">Instances</p>
        <h2>运行实例</h2>
        <p>named-map 模式支持为每个选中位点设置映射名，ordered-list 模式支持手动排序。</p>
      </div>
      <button type="button" class="secondary-button" @click="loadAll" :disabled="loading">
        {{ loading ? '刷新中' : '刷新' }}
      </button>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <form class="config-form instance-form" @submit.prevent="submit">
      <label>
        <span>实例名</span>
        <input v-model="form.name" />
      </label>
      <label>
        <span>插件名</span>
        <select v-model="form.package_name" @change="onPackageChange">
          <option value="">请先上传插件包</option>
          <option v-for="plugin in pluginPackages" :key="plugin.id" :value="plugin.name">
            {{ plugin.display_name || plugin.name }} ({{ plugin.name }})
          </option>
        </select>
      </label>
      <label>
        <span>版本</span>
        <select v-model="form.version" :disabled="pluginVersions.length === 0">
          <option value="">请选择版本</option>
          <option v-for="version in pluginVersions" :key="version.id" :value="version.version">
            {{ version.version }}
          </option>
        </select>
      </label>
      <label>
        <span>定时间隔（秒）</span>
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

        <div v-for="(binding, index) in inputBindings" :key="`in-${index}`" class="binding-card">
          <div class="binding-head">
            <strong>读取绑定 #{{ index + 1 }}</strong>
            <button type="button" class="danger-button" @click="removeInputBinding(index)">删除</button>
          </div>

          <div class="binding-basic-grid">
            <label>
              <span>绑定模式</span>
              <select v-model="binding.binding_type" @change="switchInputBindingType(binding, binding.binding_type)">
                <option value="single">单点</option>
                <option value="batch">批量</option>
              </select>
            </label>
            <label>
              <span>插件输入名</span>
              <input v-model="binding.input_name" placeholder="如 value、inputs" />
            </label>
            <label>
              <span>数据源</span>
              <select v-model="binding.data_source_id" @change="binding.source_tag = ''; binding.source_tags = []; binding.source_mappings = []">
                <option value="">请选择数据源</option>
                <option v-for="source in dataSources" :key="source.id" :value="String(source.id)">
                  {{ source.name }}
                </option>
              </select>
            </label>
          </div>

          <template v-if="binding.binding_type === 'single'">
            <div class="binding-single-grid">
              <label>
                <span>位点选择</span>
                <select v-model="binding.source_tag">
                  <option value="">请选择可读位点</option>
                  <option v-for="point in inputOptions(binding)" :key="point.tag" :value="point.tag">
                    {{ point.label }}
                  </option>
                </select>
              </label>
              <label>
                <span>手动 Redis Key / 位点</span>
                <input v-model="binding.source_tag" placeholder="如 sthb:DCS_AO_RTO_014_AI" />
              </label>
            </div>
          </template>

          <template v-else>
            <div class="binding-basic-grid">
              <label>
                <span>批量输出格式</span>
                <select v-model="binding.output_format">
                  <option value="named-map">named-map</option>
                  <option value="ordered-list">ordered-list</option>
                </select>
              </label>
              <div class="binding-actions-inline">
                <button type="button" class="secondary-button" @click="selectAllInputTags(binding)">全选位点</button>
                <button type="button" class="secondary-button" @click="clearAllInputTags(binding)">清空</button>
                <span class="muted">已选 {{ binding.source_tags.length }} 个</span>
              </div>
            </div>

            <div v-if="inputOptions(binding).length > 0" class="point-picker-grid">
              <label v-for="point in inputOptions(binding)" :key="point.tag" class="point-check">
                <input
                  type="checkbox"
                  :checked="binding.source_tags.includes(point.tag)"
                  @change="updateInputTagSelection(binding, point.tag, ($event.target as HTMLInputElement).checked)"
                />
                <span>{{ point.label }}</span>
              </label>
            </div>
            <div v-else class="empty-inline">当前数据源未配置可读位点。</div>

            <div v-if="binding.output_format === 'named-map' && binding.source_mappings.length > 0" class="mapping-table">
              <div class="mapping-head">
                <strong>named-map 映射</strong>
                <span class="muted">为每个位点填写传给插件的键名</span>
              </div>
              <div v-for="item in binding.source_mappings" :key="item.tag" class="mapping-row">
                <div class="mapping-tag">{{ item.tag }}</div>
                <input
                  class="mapping-input"
                  :value="item.key"
                  @input="updateMappingKey(binding, item.tag, ($event.target as HTMLInputElement).value)"
                  placeholder="如 input_014"
                />
              </div>
            </div>

            <div v-if="binding.output_format === 'ordered-list' && binding.source_tags.length > 0" class="mapping-table">
              <div class="mapping-head">
                <strong>ordered-list 顺序</strong>
                <span class="muted">插件收到的列表值将严格按这里的顺序排列</span>
              </div>
              <div v-for="(tag, orderIndex) in binding.source_tags" :key="tag" class="mapping-row order-row">
                <div class="mapping-tag">#{{ orderIndex + 1 }} · {{ tag }}</div>
                <div class="order-actions">
                  <button type="button" class="secondary-button small-button" @click="moveInputTag(binding, orderIndex, -1)">上移</button>
                  <button type="button" class="secondary-button small-button" @click="moveInputTag(binding, orderIndex, 1)">下移</button>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>

      <div class="wide-field binding-list">
        <div class="section-title">
          <strong>回写绑定</strong>
          <button type="button" class="secondary-button" @click="addOutputBinding">新增回写</button>
        </div>

        <div v-for="(binding, index) in outputBindings" :key="`out-${index}`" class="binding-card">
          <div class="binding-head">
            <strong>回写绑定 #{{ index + 1 }}</strong>
            <button type="button" class="danger-button" @click="removeOutputBinding(index)">删除</button>
          </div>

          <div class="binding-basic-grid">
            <label>
              <span>绑定模式</span>
              <select v-model="binding.binding_type" @change="switchOutputBindingType(binding, binding.binding_type)">
                <option value="single">单点</option>
                <option value="batch">批量</option>
              </select>
            </label>
            <label>
              <span>插件输出名</span>
              <input v-model="binding.output_name" placeholder="如 output_020、action_batch" />
            </label>
            <label>
              <span>数据源</span>
              <select v-model="binding.data_source_id" @change="binding.target_tag = ''; binding.target_tags = []">
                <option value="">请选择数据源</option>
                <option v-for="source in dataSources" :key="source.id" :value="String(source.id)">
                  {{ source.name }}
                </option>
              </select>
            </label>
            <label class="checkbox-line">
              <input v-model="binding.dry_run" type="checkbox" />
              Dry-run
            </label>
          </div>

          <template v-if="binding.binding_type === 'single'">
            <div class="binding-single-grid">
              <label>
                <span>位点选择</span>
                <select v-model="binding.target_tag">
                  <option value="">请选择可写位点</option>
                  <option v-for="point in outputOptions(binding)" :key="point.tag" :value="point.tag">
                    {{ point.label }}
                  </option>
                </select>
              </label>
              <label>
                <span>手动 Redis Key / 位点</span>
                <input v-model="binding.target_tag" placeholder="如 sthb:DCS_AO_RTO_020_AI" />
              </label>
            </div>
          </template>

          <template v-else>
            <div class="binding-actions-inline">
              <button type="button" class="secondary-button" @click="selectAllOutputTags(binding)">全选位点</button>
              <button type="button" class="secondary-button" @click="clearAllOutputTags(binding)">清空</button>
              <span class="muted">已选 {{ binding.target_tags.length }} 个</span>
            </div>
            <div class="muted small-note">批量回写时，插件输出应返回对象，键名直接使用目标位点名。</div>
            <div v-if="outputOptions(binding).length > 0" class="point-picker-grid">
              <label v-for="point in outputOptions(binding)" :key="point.tag" class="point-check">
                <input
                  type="checkbox"
                  :checked="binding.target_tags.includes(point.tag)"
                  @change="binding.target_tags = (($event.target as HTMLInputElement).checked ? [...new Set([...binding.target_tags, point.tag])] : binding.target_tags.filter((tag) => tag !== point.tag))"
                />
                <span>{{ point.label }}</span>
              </label>
            </div>
            <div v-else class="empty-inline">当前数据源未配置可写位点。</div>
          </template>
        </div>
      </div>

      <label class="json-input wide-field">
        <span>实例配置 JSON</span>
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
        <div v-for="run in recentRunsForInstance(instance)" :key="run.run_id" class="run-history-item">
          <div class="run-history-row">
            <span>{{ run.trigger_type }}</span>
            <span>{{ run.status }}</span>
            <span>{{ formatTime(run.finished_at) }}</span>
            <code>{{ run.run_id }}</code>
          </div>
          <pre>{{ stringify({ outputs: run.outputs, error: run.error }) }}</pre>
        </div>
      </div>

      <pre v-if="runResults[instance.id]">{{ stringify(runResults[instance.id]) }}</pre>
    </div>
  </section>
</template>

<style scoped>
.instances-page { max-width: 1360px; }
.instance-form { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.binding-card { display: grid; gap: 12px; padding: 14px; border: 1px solid #d8e3df; border-radius: 8px; background: #fbfdfc; }
.binding-head, .package-main, .instance-actions, .run-history-row, .mapping-head, .binding-actions-inline { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.binding-basic-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.binding-basic-grid label, .binding-single-grid label, .json-input { display: grid; gap: 8px; color: #2f403d; font-weight: 600; }
.binding-basic-grid input, .binding-basic-grid select, .binding-single-grid input, .binding-single-grid select, .mapping-input, .json-input textarea { width: 100%; padding: 10px; border: 1px solid #bacac5; border-radius: 6px; }
.binding-single-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.point-picker-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.point-check { display: flex !important; align-items: center; gap: 8px; padding: 10px 12px; border: 1px solid #d8e3df; border-radius: 8px; background: #ffffff; font-weight: 500; }
.point-check input, .checkbox-line input { width: auto; }
.small-note, .muted { font-size: 13px; color: #5e6f6c; }
.empty-inline { padding: 12px; color: #5e6f6c; background: #f7faf9; border: 1px dashed #c9d7d3; border-radius: 6px; }
.mapping-table, .run-history-item, .package-row, .status-grid > div { display: grid; gap: 10px; padding: 12px; border: 1px solid #d8e3df; border-radius: 8px; background: #ffffff; }
.mapping-row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(220px, 0.9fr); gap: 12px; align-items: center; }
.mapping-tag { padding: 10px 12px; border: 1px solid #d8e3df; border-radius: 6px; background: #f5f8f7; overflow-wrap: anywhere; }
.order-row { grid-template-columns: minmax(0, 1fr) auto; }
.order-actions { display: flex; gap: 8px; }
.small-button { min-height: 34px; padding: 0 12px; }
.package-row, .run-history, .status-grid { margin-top: 16px; }
.status-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.status-grid span { color: #5e6f6c; font-size: 13px; }
pre { white-space: pre-wrap; word-break: break-word; }
@media (max-width: 980px) {
  .instance-form, .binding-basic-grid, .binding-single-grid, .point-picker-grid, .mapping-row, .order-row, .status-grid { grid-template-columns: 1fr; }
}
</style>
