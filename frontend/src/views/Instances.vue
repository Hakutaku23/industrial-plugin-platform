<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
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

type BindingType = 'single' | 'batch' | 'history'
type BatchOutputFormat = 'named-map' | 'ordered-list'
type HistoryFillMethod = 'ffill' | 'interpolate' | 'ffill_then_interpolate' | 'none'

interface ManifestInterfaceDef {
  name: string
  type: string
  required: boolean
  description: string
  schema: Record<string, unknown> | null
}

interface ManifestInputBindingHint {
  bindingType?: BindingType
  connectorType?: 'mock' | 'redis' | 'tdengine'
  sourceTags: string[]
  lockConnectorType: boolean
  lockSourceTags: boolean
  window?: Partial<HistoryWindowConfig>
  dataSource?: Record<string, unknown>
}

interface SourceMappingRow {
  tag: string
  key: string
}

interface HistoryWindowConfig {
  start_offset_min: number
  end_offset_min: number
  sample_interval_sec: number
  lookback_before_start_sec: number
  fill_method: HistoryFillMethod
  strict_first_value: boolean
}

interface InputBindingRow {
  binding_type: BindingType
  input_name: string
  data_source_id: string
  source_tag: string
  source_tags: string[]
  source_mappings: SourceMappingRow[]
  output_format: BatchOutputFormat
  window: HistoryWindowConfig
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
  schedule_hours: 0,
  schedule_minutes: 0,
  schedule_seconds: 30,
  configText: '{}',
})
const inputBindings = ref<InputBindingRow[]>([])
const outputBindings = ref<OutputBindingRow[]>([])
let refreshTimer: number | undefined

const isInstanceModalVisible = ref(false)
const isInputBindingsModalVisible = ref(false)
const isOutputBindingsModalVisible = ref(false)
const activeInputBindingIndex = ref<number | null>(null)
const activeOutputBindingIndex = ref<number | null>(null)

const activeInputBinding = computed(() => {
  if (activeInputBindingIndex.value === null) return null
  return inputBindings.value[activeInputBindingIndex.value] ?? null
})

const activeOutputBinding = computed(() => {
  if (activeOutputBindingIndex.value === null) return null
  return outputBindings.value[activeOutputBindingIndex.value] ?? null
})

const isInputPointModalVisible = computed(() => activeInputBinding.value !== null)
const isOutputPointModalVisible = computed(() => activeOutputBinding.value !== null)
const hourOptions = Array.from({ length: 25 }, (_, index) => index)
const minuteOptions = Array.from({ length: 60 }, (_, index) => index)
const secondOptions = Array.from({ length: 60 }, (_, index) => index)
const availableMinuteOptions = computed(() => form.value.schedule_hours >= 24 ? [0] : minuteOptions)
const availableSecondOptions = computed(() => form.value.schedule_hours >= 24 ? [0] : secondOptions)
const anyModalVisible = computed(() => (
  isInstanceModalVisible.value
  || isInputBindingsModalVisible.value
  || isOutputBindingsModalVisible.value
  || isInputPointModalVisible.value
  || isOutputPointModalVisible.value
))

watch(
  () => form.value.schedule_hours,
  (hours) => {
    if (hours >= 24) {
      form.value.schedule_minutes = 0
      form.value.schedule_seconds = 0
    }
  },
)

function showCreateForm() {
  resetForm()
  isInstanceModalVisible.value = true
}

function cancelForm() {
  resetForm()
  isInstanceModalVisible.value = false
  isInputBindingsModalVisible.value = false
  isOutputBindingsModalVisible.value = false
  activeInputBindingIndex.value = null
  activeOutputBindingIndex.value = null
}

function closeInputBindingsModal() {
  isInputBindingsModalVisible.value = false
  activeInputBindingIndex.value = null
}

function closeOutputBindingsModal() {
  isOutputBindingsModalVisible.value = false
  activeOutputBindingIndex.value = null
}

function openInputBindingsModal() {
  isInputBindingsModalVisible.value = true
}

function openOutputBindingsModal() {
  isOutputBindingsModalVisible.value = true
}

function openInputPointModal(index: number) {
  activeInputBindingIndex.value = index
}

function closeInputPointModal() {
  activeInputBindingIndex.value = null
}

function openOutputPointModal(index: number) {
  activeOutputBindingIndex.value = index
}

function closeOutputPointModal() {
  activeOutputBindingIndex.value = null
}

const selectedVersionRecord = computed(
  () => pluginVersions.value.find((item) => item.version === form.value.version) ?? null,
)

const manifestInputDefs = computed(() => manifestInterfaces('inputs'))
const manifestOutputDefs = computed(() => manifestInterfaces('outputs'))

const missingRequiredInputNames = computed(() => {
  const bound = new Set(collectInputBindingNames(inputBindings.value))
  return manifestInputDefs.value
    .filter((item) => item.required && !bound.has(item.name))
    .map((item) => item.name)
})

const inputBindingCountSummary = computed(() => `${inputBindings.value.length} 条读取绑定`)
const outputBindingCountSummary = computed(() => `${outputBindings.value.length} 条回写绑定`)

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
    ensureRequiredInputBindings()
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
  ensureRequiredInputBindings()
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

function defaultInputBinding(inputName = ''): InputBindingRow {
  const binding: InputBindingRow = {
    binding_type: 'single',
    input_name: inputName,
    data_source_id: dataSources.value[0] ? String(dataSources.value[0].id) : '',
    source_tag: '',
    source_tags: [],
    source_mappings: [],
    output_format: 'named-map',
    window: defaultHistoryWindow(),
  }
  applyManifestInputBindingHint(binding)
  return binding
}

function defaultHistoryWindow(): HistoryWindowConfig {
  return {
    start_offset_min: 60,
    end_offset_min: 0,
    sample_interval_sec: 60,
    lookback_before_start_sec: 600,
    fill_method: 'ffill_then_interpolate',
    strict_first_value: true,
  }
}

function defaultOutputBinding(outputName = ''): OutputBindingRow {
  return {
    binding_type: 'single',
    output_name: outputName,
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
  if (activeInputBindingIndex.value === index) {
    activeInputBindingIndex.value = null
  } else if (activeInputBindingIndex.value !== null && activeInputBindingIndex.value > index) {
    activeInputBindingIndex.value -= 1
  }
}

function addOutputBinding() {
  outputBindings.value.push(defaultOutputBinding())
}

function removeOutputBinding(index: number) {
  outputBindings.value.splice(index, 1)
  if (activeOutputBindingIndex.value === index) {
    activeOutputBindingIndex.value = null
  } else if (activeOutputBindingIndex.value !== null && activeOutputBindingIndex.value > index) {
    activeOutputBindingIndex.value -= 1
  }
}

function switchInputBindingType(binding: InputBindingRow, type: BindingType) {
  binding.binding_type = type
  binding.source_tag = ''
  binding.source_tags = []
  binding.source_mappings = []
  if (type === 'batch') {
    binding.output_format = 'named-map'
    binding.input_name = ''
    syncManifestSourceMappings(binding)
  }
  if (type === 'history') {
    binding.output_format = 'named-map'
    binding.source_mappings = []
    if (!binding.window) binding.window = defaultHistoryWindow()
    applyManifestInputBindingHint(binding, { preserveBindingType: true })
  }
}

function switchOutputBindingType(binding: OutputBindingRow, type: BindingType) {
  binding.binding_type = type
  binding.target_tag = ''
  binding.target_tags = []
}

function onInputBindingDataSourceChange(binding: InputBindingRow) {
  binding.source_tag = ''
  binding.source_tags = []
  if (isManifestBatchBinding(binding)) {
    binding.source_mappings = binding.source_mappings.map((item) => ({ ...item, tag: '' }))
    return
  }
  binding.source_mappings = []
  applyManifestInputBindingHint(binding, { preserveBindingType: true })
}

function onInputBindingOutputFormatChange(binding: InputBindingRow) {
  binding.source_tag = ''
  binding.source_tags = []
  if (binding.output_format === 'named-map' && !binding.input_name.trim()) {
    syncManifestSourceMappings(binding)
    return
  }
  binding.source_mappings = []
}

function onBatchInputNameChange(binding: InputBindingRow) {
  if (binding.binding_type !== 'batch') return
  if (binding.output_format !== 'named-map') return
  binding.source_tag = ''
  binding.source_tags = []
  if (!binding.input_name.trim()) {
    syncManifestSourceMappings(binding)
    return
  }
  binding.source_mappings = []
}

function onInputBindingNameChange(binding: InputBindingRow) {
  applyManifestInputBindingHint(binding)
  if (binding.binding_type === 'batch') {
    onBatchInputNameChange(binding)
  }
}

function manifestInputDefByName(name: string): ManifestInterfaceDef | null {
  const normalized = name.trim()
  if (!normalized) return null
  return manifestInputDefs.value.find((item) => item.name === normalized) ?? null
}

function manifestInputBindingHint(binding: InputBindingRow): ManifestInputBindingHint | null {
  return manifestInputBindingHintByName(binding.input_name)
}

function manifestInputBindingHintByName(inputName: string): ManifestInputBindingHint | null {
  const inputDef = manifestInputDefByName(inputName)
  if (!inputDef?.schema) return null
  const schema = inputDef.schema
  const raw = firstRecord(
    schema.ippBinding,
    schema.inputBinding,
    schema['x-ipp-binding'],
    schema.binding,
  )
  if (!raw) return null

  const rawBindingType = stringValue(raw.bindingType ?? raw.binding_type).trim()
  const bindingType = ['single', 'batch', 'history'].includes(rawBindingType) ? rawBindingType as BindingType : undefined
  const rawConnectorType = stringValue(raw.connectorType ?? raw.connector_type ?? raw.requiredConnectorType ?? raw.required_connector_type).trim()
  const connectorType = ['mock', 'redis', 'tdengine'].includes(rawConnectorType) ? rawConnectorType as 'mock' | 'redis' | 'tdengine' : undefined
  const sourceTags = arrayOfStrings(raw.sourceTags ?? raw.source_tags ?? raw.requiredSourceTags ?? raw.required_source_tags)
  const windowRaw = firstRecord(raw.window, raw.windowDefaults, raw.window_defaults)
  const dataSource = firstRecord(raw.dataSource, raw.data_source, raw.datasource) ?? undefined

  return {
    bindingType,
    connectorType,
    sourceTags,
    lockConnectorType: Boolean(raw.lockConnectorType ?? raw.lock_connector_type ?? connectorType),
    lockSourceTags: Boolean(raw.lockSourceTags ?? raw.lock_source_tags ?? false),
    window: windowRaw ? normalizePartialHistoryWindow(windowRaw) : undefined,
    dataSource,
  }
}

function applyManifestInputBindingHint(
  binding: InputBindingRow,
  options: { preserveBindingType?: boolean; preserveWindow?: boolean; preserveSourceTags?: boolean } = {},
) {
  const hint = manifestInputBindingHint(binding)
  if (!hint) return

  if (!options.preserveBindingType && hint.bindingType) {
    binding.binding_type = hint.bindingType
  }
  if (hint.bindingType === 'history' || hint.connectorType === 'tdengine') {
    binding.binding_type = 'history'
  }
  if (hint.connectorType) {
    const matched = dataSources.value.find((source) => source.connector_type === hint.connectorType)
    const current = findDataSource(binding.data_source_id)
    if (!current || current.connector_type !== hint.connectorType) {
      binding.data_source_id = matched ? String(matched.id) : ''
    }
  }
  if (hint.sourceTags.length > 0 && !options.preserveSourceTags) {
    binding.source_tags = [...hint.sourceTags]
    if (binding.binding_type === 'batch') {
      syncSourceMappings(binding)
    }
  }
  if (hint.window && !options.preserveWindow) {
    binding.window = { ...defaultHistoryWindow(), ...binding.window, ...hint.window }
  }
}

function normalizePartialHistoryWindow(value: Record<string, unknown>): Partial<HistoryWindowConfig> {
  const result: Partial<HistoryWindowConfig> = {}
  if ('start_offset_min' in value || 'startOffsetMin' in value) {
    result.start_offset_min = normalizeBoundedNumber(value.start_offset_min ?? value.startOffsetMin, 60, 1, 10080)
  }
  if ('end_offset_min' in value || 'endOffsetMin' in value) {
    result.end_offset_min = normalizeBoundedNumber(value.end_offset_min ?? value.endOffsetMin, 0, 0, 10079)
  }
  if ('sample_interval_sec' in value || 'sampleIntervalSec' in value) {
    result.sample_interval_sec = normalizeBoundedNumber(value.sample_interval_sec ?? value.sampleIntervalSec, 60, 1, 86400)
  }
  if ('lookback_before_start_sec' in value || 'lookbackBeforeStartSec' in value) {
    result.lookback_before_start_sec = normalizeBoundedNumber(value.lookback_before_start_sec ?? value.lookbackBeforeStartSec, 600, 0, 86400)
  }
  const rawFillMethod = stringValue(value.fill_method ?? value.fillMethod).trim()
  if (['ffill', 'interpolate', 'ffill_then_interpolate', 'none'].includes(rawFillMethod)) {
    result.fill_method = rawFillMethod as HistoryFillMethod
  }
  if ('strict_first_value' in value || 'strictFirstValue' in value) {
    result.strict_first_value = Boolean(value.strict_first_value ?? value.strictFirstValue)
  }
  return result
}

function historyTagsFromManifest(binding: InputBindingRow) {
  return manifestInputBindingHint(binding)?.sourceTags ?? []
}

function hasManifestHistoryTags(binding: InputBindingRow) {
  return historyTagsFromManifest(binding).length > 0
}

function applyManifestHistoryTags(binding: InputBindingRow) {
  const tags = historyTagsFromManifest(binding)
  if (tags.length > 0) {
    binding.source_tags = [...tags]
  }
}

function dataSourceAllowedForInputBinding(binding: InputBindingRow, source: DataSourceRecord) {
  const hint = manifestInputBindingHint(binding)
  if (!hint) return true
  if (hint.connectorType && source.connector_type !== hint.connectorType) return false
  return dataSourceMatchesManifestHint(source, hint)
}

function dataSourceMatchesManifestHint(source: DataSourceRecord, hint: ManifestInputBindingHint) {
  const rule = hint.dataSource
  if (!rule) return true
  const expectedDatabase = stringValue(rule.database).trim()
  const expectedTable = stringValue(rule.table_name ?? rule.tableName).trim()
  if (expectedDatabase && stringValue(source.config.database).trim() !== expectedDatabase) return false
  if (expectedTable) {
    const actualTable = stringValue(source.config.table_name ?? source.config.tableName).trim()
    if (actualTable !== expectedTable) return false
  }
  return true
}

function validateInputDataSourceConstraints(bindings: InputBindingRow[]) {
  for (const binding of bindings) {
    const hint = manifestInputBindingHint(binding)
    if (!hint) continue
    const source = findDataSource(binding.data_source_id)
    if (hint.connectorType && (!source || source.connector_type !== hint.connectorType)) {
      throw new Error(`插件输入 ${binding.input_name} 要求绑定 ${hint.connectorType} 数据源`)
    }
    if (source && !dataSourceMatchesManifestHint(source, hint)) {
      throw new Error(`插件输入 ${binding.input_name} 绑定的数据源不符合 manifest 固化的数据库/表配置`)
    }
    if (hint.bindingType && binding.binding_type !== hint.bindingType) {
      throw new Error(`插件输入 ${binding.input_name} 要求使用 ${hint.bindingType} 绑定模式`)
    }
    if (hint.sourceTags.length > 0) {
      const selected = new Set(binding.source_tags.map((tag) => tag.trim()).filter(Boolean))
      const missing = hint.sourceTags.filter((tag) => !selected.has(tag))
      if (hint.lockSourceTags && missing.length > 0) {
        throw new Error(`插件输入 ${binding.input_name} 缺少 manifest 声明位点: ${missing.join(', ')}`)
      }
    }
  }
}

function firstRecord(...values: unknown[]): Record<string, unknown> | null {
  for (const value of values) {
    if (isRecord(value)) return value
  }
  return null
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

function isManifestBatchBinding(binding: InputBindingRow) {
  return (
    binding.binding_type === 'batch'
    && binding.output_format === 'named-map'
    && !binding.input_name.trim()
    && manifestInputDefs.value.length > 0
  )
}

function syncSourceTagsFromMappings(binding: InputBindingRow) {
  binding.source_tags = Array.from(
    new Set(
      binding.source_mappings
        .map((item) => item.tag.trim())
        .filter(Boolean),
    ),
  )
}

function syncManifestSourceMappings(binding: InputBindingRow) {
  if (!isManifestBatchBinding(binding)) return
  const previous = new Map(
    binding.source_mappings.map((item) => [item.key.trim(), item.tag.trim()]),
  )
  binding.source_mappings = manifestInputDefs.value.map((item) => ({
    key: item.name,
    tag: previous.get(item.name) ?? '',
  }))
  syncSourceTagsFromMappings(binding)
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

function clearManifestInputMappings(binding: InputBindingRow) {
  binding.source_mappings = binding.source_mappings.map((item) => ({ ...item, tag: '' }))
  binding.source_tags = []
}

function updateManifestMappingTag(binding: InputBindingRow, key: string, value: string) {
  const next = value.trim()
  binding.source_mappings = binding.source_mappings.map((item) =>
    item.key === key ? { ...item, tag: next } : item,
  )
  syncSourceTagsFromMappings(binding)
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

function manifestInterfaces(kind: 'inputs' | 'outputs'): ManifestInterfaceDef[] {
  const manifest = selectedVersionRecord.value?.manifest
  if (!isRecord(manifest) || !isRecord(manifest.spec)) return []
  const raw = manifest.spec[kind]
  if (!Array.isArray(raw)) return []
  return raw
    .filter((item): item is Record<string, unknown> => isRecord(item))
    .map((item) => ({
      name: stringValue(item.name).trim(),
      type: stringValue(item.type).trim(),
      required: Boolean(item.required),
      description: stringValue(item.description).trim(),
      schema: isRecord(item.schema) ? item.schema : null,
    }))
    .filter((item) => item.name)
}

function ensureRequiredInputBindings() {
  for (const binding of inputBindings.value) {
    syncManifestSourceMappings(binding)
  }
}

function isRequiredInputName(name: string) {
  return manifestInputDefs.value.some((item) => item.name === name && item.required)
}

function collectInputBindingNames(bindings: Array<Record<string, unknown>>) {
  const names: string[] = []
  for (const binding of bindings) {
    const bindingType = stringValue(binding.binding_type || 'single')
    const inputName = stringValue(binding.input_name).trim()
    const outputFormat = stringValue(binding.output_format || 'named-map').trim()
    if (bindingType === 'batch' && outputFormat === 'named-map' && !inputName) {
      const sourceMappings = Array.isArray(binding.source_mappings)
        ? binding.source_mappings
            .filter((item): item is Record<string, unknown> => isRecord(item))
            .map((item) => stringValue(item.key).trim())
            .filter(Boolean)
        : []
      names.push(...sourceMappings)
      continue
    }
    if (inputName) names.push(inputName)
  }
  return Array.from(new Set(names))
}

function inputBindingHasPayload(binding: InputBindingRow) {
  if (binding.binding_type === 'single') {
    return Boolean(binding.input_name.trim())
  }
  if (binding.binding_type === 'history') {
    return Boolean(binding.input_name.trim()) && binding.source_tags.some((tag) => tag.trim())
  }
  if (binding.output_format === 'named-map' && !binding.input_name.trim()) {
    return binding.source_mappings.some((item) => item.tag.trim() || item.key.trim())
  }
  return Boolean(binding.input_name.trim())
}

function validateManifestBindings(
  normalizedInputs: Array<Record<string, unknown>>,
  normalizedOutputs: Array<{ output_name: string }>,
) {
  const inputNames = collectInputBindingNames(normalizedInputs)
  const outputNames = normalizedOutputs.map((binding) => binding.output_name)

  const duplicateInputNames = duplicateNames(inputNames)
  if (duplicateInputNames.length > 0) {
    throw new Error(`插件输入绑定重复: ${duplicateInputNames.join(', ')}`)
  }

  const duplicateOutputNames = duplicateNames(outputNames)
  if (duplicateOutputNames.length > 0) {
    throw new Error(`插件输出绑定重复: ${duplicateOutputNames.join(', ')}`)
  }

  if (manifestInputDefs.value.length > 0) {
    const declaredInputs = new Set(manifestInputDefs.value.map((item) => item.name))
    const missingRequired = manifestInputDefs.value
      .filter((item) => item.required && !inputNames.includes(item.name))
      .map((item) => item.name)
    if (missingRequired.length > 0) {
      throw new Error(`缺少必填插件输入绑定: ${missingRequired.join(', ')}`)
    }

    const unknownInputs = Array.from(new Set(inputNames.filter((name) => !declaredInputs.has(name))))
    if (unknownInputs.length > 0) {
      throw new Error(`存在未在 manifest 中声明的插件输入: ${unknownInputs.join(', ')}`)
    }
  }

  if (manifestOutputDefs.value.length > 0) {
    const declaredOutputs = new Set(manifestOutputDefs.value.map((item) => item.name))
    const unknownOutputs = Array.from(new Set(outputNames.filter((name) => !declaredOutputs.has(name))))
    if (unknownOutputs.length > 0) {
      throw new Error(`存在未在 manifest 中声明的插件输出: ${unknownOutputs.join(', ')}`)
    }
  }
}

function duplicateNames(values: string[]) {
  const seen = new Set<string>()
  const duplicates = new Set<string>()
  for (const value of values) {
    if (seen.has(value)) duplicates.add(value)
    else seen.add(value)
  }
  return Array.from(duplicates)
}

async function submit() {
  saving.value = true
  error.value = ''
  try {
    if (!form.value.name.trim()) throw new Error('请填写实例名')
    if (!form.value.package_name || !form.value.version) throw new Error('请选择插件和版本')
    validateInputDataSourceConstraints(inputBindings.value)

    const normalizedInputBindings = inputBindings.value
      .filter((binding) => binding.data_source_id && inputBindingHasPayload(binding))
      .map((binding) => {
        if (binding.binding_type === 'history') {
          const input_name = binding.input_name.trim()
          const source_tags = Array.from(new Set(binding.source_tags.map((tag) => tag.trim()).filter(Boolean)))
          if (!input_name) throw new Error('TDEngine 历史读取必须指定插件输入名')
          if (source_tags.length === 0) throw new Error(`TDEngine 历史读取绑定 ${input_name} 未选择任何位点`)
          const windowConfig = normalizeHistoryWindow(binding.window)
          if (windowConfig.start_offset_min <= windowConfig.end_offset_min) {
            throw new Error('TDEngine 历史读取的起点偏移必须大于终点偏移')
          }
          if (windowConfig.sample_interval_sec <= 0) {
            throw new Error('TDEngine 历史读取的点间隔必须大于 0 秒')
          }
          return {
            binding_type: 'history' as const,
            input_name,
            data_source_id: Number(binding.data_source_id),
            source_tags,
            window: windowConfig,
          }
        }
        if (binding.binding_type === 'batch') {
          const input_name = binding.input_name.trim()
          const source_tags = Array.from(new Set(binding.source_tags.map((tag) => tag.trim()).filter(Boolean)))
          if (binding.output_format === 'named-map') {
            const source_mappings = binding.source_mappings
              .map((item) => ({ tag: item.tag.trim(), key: item.key.trim() }))
              .filter((item) => item.tag && item.key)
            if (source_mappings.length === 0) {
              throw new Error('批量读取绑定未完成 named-map 映射')
            }
            const keys = source_mappings.map((item) => item.key)
            if (new Set(keys).size !== keys.length) {
              throw new Error('批量读取绑定的 named-map 键名重复')
            }
            if (!input_name) {
              return {
                binding_type: 'batch' as const,
                data_source_id: Number(binding.data_source_id),
                source_mappings,
                output_format: 'named-map' as const,
              }
            }
            return {
              binding_type: 'batch' as const,
              input_name,
              data_source_id: Number(binding.data_source_id),
              source_tags: source_tags.length > 0 ? source_tags : source_mappings.map((item) => item.tag),
              source_mappings,
              output_format: 'named-map' as const,
            }
          }
          if (!input_name) throw new Error('ordered-list 批量读取必须指定插件输入名')
          if (source_tags.length === 0) throw new Error(`批量读取绑定 ${input_name} 未选择任何位点`)
          return {
            binding_type: 'batch' as const,
            input_name,
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

    validateManifestBindings(normalizedInputBindings, normalizedOutputBindings)

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
      schedule_interval_sec: schedulePartsToSeconds(),
    })
    await loadAll()
    cancelForm()
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
    if (editingInstanceId.value === instance.id) cancelForm()
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
    ...splitScheduleInterval(instance.schedule_interval_sec || 30),
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
      window: normalizeHistoryWindow(record.window),
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
  ensureRequiredInputBindings()
  for (const binding of inputBindings.value) {
    applyManifestInputBindingHint(binding, { preserveBindingType: true, preserveWindow: true })
  }
  applyDefaultDataSource()
  isInstanceModalVisible.value = true
}

function normalizeSourceMappings(value: unknown, sourceTags: string[]) {
  const mappings = Array.isArray(value)
    ? value
        .filter((item): item is Record<string, unknown> => isRecord(item))
        .map((item) => ({ tag: stringValue(item.tag), key: stringValue(item.key) }))
        .filter((item) => item.tag || item.key)
    : []
  return mappings.length > 0 ? mappings : sourceTags.map((tag) => ({ tag, key: sanitizePointKey(tag) }))
}

function normalizeBindingType(value: unknown): BindingType {
  if (value === 'batch') return 'batch'
  if (value === 'history') return 'history'
  return 'single'
}

function normalizeHistoryWindow(value: unknown): HistoryWindowConfig {
  const record = isRecord(value) ? value : {}
  return {
    start_offset_min: normalizeBoundedNumber(record.start_offset_min, 60, 1, 10080),
    end_offset_min: normalizeBoundedNumber(record.end_offset_min, 0, 0, 10080),
    sample_interval_sec: normalizeBoundedNumber(record.sample_interval_sec, 60, 1, 86400),
    lookback_before_start_sec: normalizeBoundedNumber(record.lookback_before_start_sec, 600, 0, 86400),
    fill_method: normalizeHistoryFillMethod(record.fill_method),
    strict_first_value: typeof record.strict_first_value === 'boolean' ? record.strict_first_value : true,
  }
}

function normalizeBoundedNumber(value: unknown, fallback: number, min: number, max: number): number {
  const numberValue = Math.floor(Number(value))
  if (!Number.isFinite(numberValue)) return fallback
  return Math.min(max, Math.max(min, numberValue))
}

function normalizeHistoryFillMethod(value: unknown): HistoryFillMethod {
  if (value === 'ffill' || value === 'interpolate' || value === 'ffill_then_interpolate' || value === 'none') {
    return value
  }
  return 'ffill_then_interpolate'
}

function normalizeOutputFormat(value: unknown): BatchOutputFormat {
  return value === 'ordered-list' ? 'ordered-list' : 'named-map'
}

function normalizeSchedulePart(value: unknown, min: number, max: number): number {
  const numberValue = Math.floor(Number(value))
  if (!Number.isFinite(numberValue)) return min
  return Math.min(max, Math.max(min, numberValue))
}

function splitScheduleInterval(totalSeconds: number) {
  const normalized = Math.min(86400, Math.max(5, Math.floor(Number(totalSeconds) || 30)))
  return {
    schedule_hours: Math.floor(normalized / 3600),
    schedule_minutes: Math.floor((normalized % 3600) / 60),
    schedule_seconds: normalized % 60,
  }
}

function schedulePartsToSeconds(): number {
  const hours = normalizeSchedulePart(form.value.schedule_hours, 0, 24)
  const minutes = hours >= 24 ? 0 : normalizeSchedulePart(form.value.schedule_minutes, 0, 59)
  const seconds = hours >= 24 ? 0 : normalizeSchedulePart(form.value.schedule_seconds, 0, 59)
  const total = hours * 3600 + minutes * 60 + seconds
  if (total < 5) throw new Error('定时间隔不能小于 5 秒')
  if (total > 86400) throw new Error('定时间隔不能超过 24 小时')
  form.value.schedule_interval_sec = total
  form.value.schedule_hours = hours
  form.value.schedule_minutes = minutes
  form.value.schedule_seconds = seconds
  return total
}

function formatScheduleInterval(totalSeconds: number): string {
  const normalized = Math.min(86400, Math.max(0, Math.floor(Number(totalSeconds) || 0)))
  const hours = Math.floor(normalized / 3600)
  const minutes = Math.floor((normalized % 3600) / 60)
  const seconds = normalized % 60
  const parts: string[] = []
  if (hours > 0) parts.push(`${hours} 小时`)
  if (minutes > 0) parts.push(`${minutes} 分钟`)
  if (seconds > 0 || parts.length === 0) parts.push(`${seconds} 秒`)
  return parts.join(' ')
}

function resetForm() {
  const defaultSchedule = splitScheduleInterval(30)
  editingInstanceId.value = null
  form.value = {
    name: 'demo-instance',
    package_name: pluginPackages.value[0]?.name ?? '',
    version: pluginPackages.value[0]?.latest_version ?? '',
    writeback_enabled: false,
    schedule_enabled: false,
    schedule_interval_sec: 30,
    ...defaultSchedule,
    configText: '{}',
  }
  inputBindings.value = []
  outputBindings.value = []
  ensureRequiredInputBindings()
  applyDefaultDataSource()
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

function describeInputBinding(binding: InputBindingRow) {
  if (binding.binding_type === 'single') {
    return binding.source_tag ? `单点 · ${binding.source_tag}` : '单点 · 未配置位点'
  }
  if (binding.binding_type === 'history') {
    const window = normalizeHistoryWindow(binding.window)
    return `历史窗口 · ${binding.source_tags.length} 个位点 · ${window.start_offset_min}→${window.end_offset_min} 分钟 · ${window.sample_interval_sec}s 间隔`
  }
  if (binding.output_format === 'ordered-list') {
    return `批量列表 · ${binding.source_tags.length} 个位点`
  }
  if (isManifestBatchBinding(binding)) {
    const configured = binding.source_mappings.filter((item) => item.tag.trim()).length
    return `批量映射 · ${configured}/${binding.source_mappings.length} 已配置`
  }
  return `批量映射 · ${binding.source_mappings.length} 项`
}

function describeOutputBinding(binding: OutputBindingRow) {
  if (binding.binding_type === 'single') {
    return binding.target_tag ? `单点 · ${binding.target_tag}` : '单点 · 未配置位点'
  }
  return `批量回写 · ${binding.target_tags.length} 个位点`
}


function handleModalEscape(event: KeyboardEvent) {
  if (event.key !== 'Escape') return
  if (activeInputBinding.value) {
    closeInputPointModal()
    return
  }
  if (activeOutputBinding.value) {
    closeOutputPointModal()
    return
  }
  if (isInputBindingsModalVisible.value) {
    closeInputBindingsModal()
    return
  }
  if (isOutputBindingsModalVisible.value) {
    closeOutputBindingsModal()
    return
  }
  if (isInstanceModalVisible.value) {
    cancelForm()
  }
}

watch(
  manifestInputDefs,
  () => {
    ensureRequiredInputBindings()
  },
  { deep: true },
)

watch(
  dataSources,
  () => {
    applyDefaultDataSource()
  },
  { deep: true },
)


watch(
  anyModalVisible,
  (visible) => {
    if (typeof document === 'undefined') return
    document.body.style.overflow = visible ? 'hidden' : ''
  },
  { immediate: true },
)

onMounted(() => {
  loadAll()
  window.addEventListener('keydown', handleModalEscape)
  refreshTimer = window.setInterval(() => {
    if (!anyModalVisible.value) {
      loadAll()
    }
  }, 5000)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleModalEscape)
  if (refreshTimer !== undefined) window.clearInterval(refreshTimer)
  if (typeof document !== 'undefined') {
    document.body.style.overflow = ''
  }
})
</script>

<template>
  <section class="panel instances-page">
    <div class="intro page-heading">
      <div class="heading-text">
        <p class="eyebrow">OBSERVABILITY</p>
        <h2>实例管理 (Instance Operations)</h2>
        <p class="subtitle">管理工业插件的运行实例。配置位点绑定、执行定时任务或手动触发实例运行。</p>
      </div>
      <div class="header-actions">
        <button type="button" class="secondary-button" @click="loadAll" :disabled="loading">
          {{ loading ? '↻ 刷新中...' : '↻ 刷新状态' }}
        </button>
        <button type="button" class="primary-button" @click="showCreateForm">
          + 创建新实例
        </button>
      </div>
    </div>

    <div v-if="error" class="error-banner">⚠ {{ error }}</div>

    <div v-if="instances.length === 0" class="empty-state">
      <p>当前环境无正在运行的实例</p>
      <button type="button" class="primary-button" @click="showCreateForm">+ 立即创建一个</button>
    </div>

    <div v-else class="instances-grid">
      <div v-for="instance in instances" :key="instance.id" class="instance-card">
        <div class="card-header">
          <div class="card-title-wrap">
            <h3>{{ instance.name }}</h3>
            <span class="version-badge">{{ instance.package_name }} @ {{ instance.version }}</span>
          </div>
          <div class="status-indicator">
            <span class="status-dot" :class="{ running: instance.status === 'running', stopped: instance.status === 'stopped', error: instance.status === 'error' }"></span>
            {{ instance.status === 'running' ? 'ONLINE' : (instance.status === 'stopped' ? 'OFFLINE' : instance.status) }}
          </div>
        </div>

        <div class="card-body">
          <div class="info-row">
            <span class="info-label">回写策略</span>
            <span class="info-value" :class="{ 'text-danger': instance.writeback_enabled, 'text-success': !instance.writeback_enabled }">
              {{ instance.writeback_enabled ? '⚠ 允许真实回写' : '🛡 仅 Dry-run' }}
            </span>
          </div>
          <div class="info-row">
            <span class="info-label">定时规则</span>
            <span class="info-value">
              {{ instance.schedule_enabled ? `⏱ 每 ${formatScheduleInterval(instance.schedule_interval_sec)}` : '⏸ 未启用定时' }}
            </span>
          </div>

          <div class="schedule-times">
            <div class="time-box">
              <span class="time-label">上次运行</span>
              <span class="time-val">{{ formatTime(instance.last_scheduled_run_at) }}</span>
            </div>
            <div class="time-box">
              <span class="time-label">下次执行</span>
              <span class="time-val">{{ formatTime(instance.next_scheduled_run_at) }}</span>
            </div>
          </div>
        </div>

        <div class="card-actions-bar">
          <button type="button" class="btn-icon" title="修改" @click="editInstance(instance)">⚙ 配置</button>
          <button type="button" class="btn-icon" title="手动运行" @click="run(instance)" :disabled="runningId === instance.id">
            {{ runningId === instance.id ? '⏳...' : '▶ 运行' }}
          </button>
          <button v-if="instance.schedule_enabled" type="button" class="btn-icon text-warning" title="停止定时" @click="stopSchedule(instance)" :disabled="operatingId === instance.id">
            ⏸ 停用
          </button>
          <button v-else type="button" class="btn-icon text-success" title="启动定时" @click="startSchedule(instance)" :disabled="operatingId === instance.id">
            ⏱ 启用
          </button>
          <button type="button" class="btn-icon text-danger" title="删除实例" @click="removeInstance(instance)" :disabled="operatingId === instance.id">
            🗑 删除
          </button>
        </div>

        <details class="run-history-expander">
          <summary>查看最近运行记录 ({{ recentRunsForInstance(instance).length }})</summary>
          <div class="run-history-content">
            <div v-if="recentRunsForInstance(instance).length === 0" class="muted empty-history">
              暂无运行记录，定时触发后这里会自动刷新。
            </div>
            <div v-for="run in recentRunsForInstance(instance)" :key="run.run_id" class="history-item">
              <div class="history-item-head">
                <span class="run-type">[{{ run.trigger_type }}]</span>
                <span class="run-status" :class="run.status">{{ run.status === 'error' ? 'FAILED' : run.status }}</span>
                <span class="run-time">{{ formatTime(run.finished_at) }}</span>
              </div>
              <pre class="run-logs">{{ stringify({ outputs: run.outputs, error: run.error }) }}</pre>
            </div>
          </div>
        </details>

        <div v-if="runResults[instance.id]" class="manual-run-result">
          <p class="result-title">最新手动运行结果:</p>
          <pre>{{ stringify(runResults[instance.id]) }}</pre>
        </div>
      </div>
    </div>

    <Transition name="modal-fade" appear>
    <div v-if="isInstanceModalVisible" class="modal-mask" @click.self="cancelForm">
      <div class="modal-shell instance-modal-shell">
        <div class="modal-header">
          <h3>{{ editingInstanceId ? '⚙ 修改实例配置' : '✨ 创建新实例' }}</h3>
          <button type="button" class="secondary-button small-button" @click="cancelForm">关闭</button>
        </div>

        <div class="modal-body">
          <div class="form-panel">
            <h4 class="panel-title">基础配置</h4>
            <div class="instance-form-grid">
              <label>
                <span>实例名</span>
                <input v-model="form.name" required placeholder="如 demo-instance" />
              </label>
              <label>
                <span>插件名</span>
                <select v-model="form.package_name" @change="onPackageChange" required>
                  <option value="">请先上传插件包</option>
                  <option v-for="plugin in pluginPackages" :key="plugin.id" :value="plugin.name">
                    {{ plugin.display_name || plugin.name }} ({{ plugin.name }})
                  </option>
                </select>
              </label>
              <label>
                <span>版本</span>
                <select v-model="form.version" :disabled="pluginVersions.length === 0" required>
                  <option value="">请选择版本</option>
                  <option v-for="version in pluginVersions" :key="version.id" :value="version.version">
                    {{ version.version }}
                  </option>
                </select>
              </label>
              <div class="schedule-picker">
                <span class="schedule-picker-title">定时间隔</span>
                <div class="schedule-select-row">
                  <label>
                    <select v-model.number="form.schedule_hours">
                      <option v-for="hour in hourOptions" :key="hour" :value="hour">{{ hour }}</option>
                    </select>
                    <span>小时</span>
                  </label>
                  <label>
                    <select v-model.number="form.schedule_minutes">
                      <option v-for="minute in availableMinuteOptions" :key="minute" :value="minute">{{ minute }}</option>
                    </select>
                    <span>分钟</span>
                  </label>
                  <label>
                    <select v-model.number="form.schedule_seconds">
                      <option v-for="second in availableSecondOptions" :key="second" :value="second">{{ second }}</option>
                    </select>
                    <span>秒</span>
                  </label>
                </div>
                <p class="small-note schedule-note">保存时自动转换为秒，范围为 5 秒到 24 小时。</p>
              </div>
              <label class="checkbox-box">
                <input v-model="form.schedule_enabled" type="checkbox" />
                <span>启用定时运行</span>
              </label>
              <label class="checkbox-box">
                <input v-model="form.writeback_enabled" type="checkbox" />
                <span :class="{ 'text-danger': form.writeback_enabled }">允许真实回写 (开启后将真实写入数据)</span>
              </label>
            </div>
          </div>

          <div v-if="selectedVersionRecord" class="form-panel manifest-summary-panel">
            <h4 class="panel-title">接口规范 (Manifest)</h4>
            <div class="manifest-summary">
              <div class="manifest-block">
                <div class="manifest-head">
                  <strong>📥 Manifest 输入</strong>
                  <span class="muted">带 * 的为必填项</span>
                </div>
                <div v-if="manifestInputDefs.length > 0" class="manifest-chip-grid">
                  <div v-for="item in manifestInputDefs" :key="item.name" class="manifest-chip" :class="{ required: item.required }">
                    <span>{{ item.name }}</span>
                    <small>{{ item.type || 'unknown' }}</small>
                  </div>
                </div>
                <div v-else class="empty-inline">当前版本未声明输入接口。</div>
                <p v-if="missingRequiredInputNames.length > 0" class="error-inline">
                  ⚠ 缺少必填输入绑定：{{ missingRequiredInputNames.join(', ') }}
                </p>
              </div>

              <div class="manifest-block">
                <div class="manifest-head">
                  <strong>📤 Manifest 输出</strong>
                  <span class="muted">回写绑定只能选此处声明的输出名</span>
                </div>
                <div v-if="manifestOutputDefs.length > 0" class="manifest-chip-grid">
                  <div v-for="item in manifestOutputDefs" :key="item.name" class="manifest-chip">
                    <span>{{ item.name }}</span>
                    <small>{{ item.type || 'unknown' }}</small>
                  </div>
                </div>
                <div v-else class="empty-inline">当前版本未声明输出接口。</div>
              </div>
            </div>
          </div>

          <div class="form-panel binding-summary-panel">
            <div class="binding-summary-card">
              <div>
                <h4 class="panel-title">📥 读取绑定</h4>
                <p class="muted">{{ inputBindingCountSummary }}</p>
                <div class="binding-summary-list">
                  <span v-for="(binding, index) in inputBindings" :key="`input-summary-${index}`" class="summary-pill">
                    #{{ index + 1 }} · {{ binding.input_name || '批量映射' }} · {{ describeInputBinding(binding) }}
                  </span>
                  <span v-if="inputBindings.length === 0" class="muted">暂无读取绑定</span>
                </div>
              </div>
              <button type="button" class="secondary-button" @click="openInputBindingsModal">配置读取绑定</button>
            </div>

            <div class="binding-summary-card">
              <div>
                <h4 class="panel-title">📤 回写绑定</h4>
                <p class="muted">{{ outputBindingCountSummary }}</p>
                <div class="binding-summary-list">
                  <span v-for="(binding, index) in outputBindings" :key="`output-summary-${index}`" class="summary-pill">
                    #{{ index + 1 }} · {{ binding.output_name || '未命名输出' }} · {{ describeOutputBinding(binding) }}
                  </span>
                  <span v-if="outputBindings.length === 0" class="muted">暂无回写绑定</span>
                </div>
              </div>
              <button type="button" class="secondary-button" @click="openOutputBindingsModal">配置回写绑定</button>
            </div>
          </div>

          <div class="form-panel">
            <h4 class="panel-title">附加配置 (JSON)</h4>
            <label class="json-input wide-field">
              <textarea v-model="form.configText" rows="4" spellcheck="false" placeholder="在此输入自定义 JSON 配置..."></textarea>
            </label>
          </div>
        </div>

        <div class="modal-footer">
          <button type="button" class="secondary-button" @click="cancelForm">取消编辑</button>
          <button type="button" class="primary-button" :disabled="saving" @click="submit">
            {{ saving ? '🔄 保存中...' : (editingInstanceId ? '💾 保存修改' : '✨ 确认创建') }}
          </button>
        </div>
      </div>
    </div>
    </Transition>

    <Transition name="modal-fade" appear>
    <div v-if="isInputBindingsModalVisible" class="modal-mask" @click.self="closeInputBindingsModal">
      <div class="modal-shell binding-modal-shell">
        <div class="modal-header">
          <h3>📥 读取绑定配置</h3>
          <div class="header-actions">
            <button type="button" class="secondary-button" @click="addInputBinding">+ 新增读取绑定</button>
            <button type="button" class="secondary-button small-button" @click="closeInputBindingsModal">关闭</button>
          </div>
        </div>
        <div class="modal-body binding-list-modal-body">
          <div v-if="inputBindings.length === 0" class="empty-inline">暂无读取绑定，点击右上角按钮添加。</div>
          <div v-for="(binding, index) in inputBindings" :key="`input-list-${index}`" class="binding-list-card">
            <div class="binding-head">
              <div class="binding-title-line">
                <strong>绑定 #{{ index + 1 }}</strong>
                <span v-if="binding.input_name && isRequiredInputName(binding.input_name)" class="required-badge">必填</span>
              </div>
              <div class="binding-list-actions">
                <button type="button" class="secondary-button" @click="openInputPointModal(index)">配置点位</button>
                <button type="button" class="danger-button" @click="removeInputBinding(index)">删除</button>
              </div>
            </div>
            <div class="binding-basic-grid compact-grid">
              <label>
                <span>绑定模式</span>
                <select v-model="binding.binding_type" @change="switchInputBindingType(binding, binding.binding_type)">
                  <option value="single">单点</option>
                  <option value="batch">批量</option>
                  <option value="history">TDEngine 历史窗口</option>
                </select>
              </label>
              <label>
                <span>插件输入名</span>
                <select v-if="manifestInputDefs.length > 0" v-model="binding.input_name" @change="onInputBindingNameChange(binding)">
                  <option :value="''">{{ binding.binding_type === 'batch' ? '按 manifest 输入列表逐项映射' : '请选择 manifest 输入' }}</option>
                  <option v-for="item in manifestInputDefs" :key="item.name" :value="item.name">
                    {{ item.required ? `${item.name} *` : item.name }}
                  </option>
                </select>
                <input v-else v-model="binding.input_name" placeholder="如 value、inputs" />
              </label>
              <label>
                <span>数据源</span>
                <select v-model="binding.data_source_id" @change="onInputBindingDataSourceChange(binding)">
                  <option value="">请选择数据源</option>
                  <option
                    v-for="source in dataSources"
                    :key="source.id"
                    :value="String(source.id)"
                    :disabled="!dataSourceAllowedForInputBinding(binding, source)"
                  >
                    {{ source.name }} · {{ source.connector_type }}
                  </option>
                </select>
              </label>
              <div class="summary-box">
                <span class="time-label">当前配置</span>
                <strong>{{ describeInputBinding(binding) }}</strong>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    </Transition>

    <Transition name="modal-fade" appear>
    <div v-if="isOutputBindingsModalVisible" class="modal-mask" @click.self="closeOutputBindingsModal">
      <div class="modal-shell binding-modal-shell">
        <div class="modal-header">
          <h3>📤 回写绑定配置</h3>
          <div class="header-actions">
            <button type="button" class="secondary-button" @click="addOutputBinding">+ 新增回写绑定</button>
            <button type="button" class="secondary-button small-button" @click="closeOutputBindingsModal">关闭</button>
          </div>
        </div>
        <div class="modal-body binding-list-modal-body">
          <div v-if="outputBindings.length === 0" class="empty-inline">暂无回写绑定，点击右上角按钮添加。</div>
          <div v-for="(binding, index) in outputBindings" :key="`output-list-${index}`" class="binding-list-card">
            <div class="binding-head">
              <strong>绑定 #{{ index + 1 }}</strong>
              <div class="binding-list-actions">
                <button type="button" class="secondary-button" @click="openOutputPointModal(index)">配置点位</button>
                <button type="button" class="danger-button" @click="removeOutputBinding(index)">删除</button>
              </div>
            </div>
            <div class="binding-basic-grid compact-grid">
              <label>
                <span>绑定模式</span>
                <select v-model="binding.binding_type" @change="switchOutputBindingType(binding, binding.binding_type)">
                  <option value="single">单点</option>
                  <option value="batch">批量</option>
                </select>
              </label>
              <label>
                <span>插件输出名</span>
                <select v-if="manifestOutputDefs.length > 0" v-model="binding.output_name">
                  <option value="">请选择 manifest 输出</option>
                  <option v-for="item in manifestOutputDefs" :key="item.name" :value="item.name">
                    {{ item.name }}
                  </option>
                </select>
                <input v-else v-model="binding.output_name" placeholder="如 output_020" />
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
              <div class="summary-box">
                <span class="time-label">当前配置</span>
                <strong>{{ describeOutputBinding(binding) }}</strong>
              </div>
            </div>
            <label class="checkbox-box dryrun-box">
              <input v-model="binding.dry_run" type="checkbox" />
              <span>Dry-run (阻断写)</span>
            </label>
          </div>
        </div>
      </div>
    </div>
    </Transition>

    <Transition name="modal-fade" appear>
    <div v-if="activeInputBinding" class="modal-mask" @click.self="closeInputPointModal">
      <div class="modal-shell point-modal-shell">
        <div class="modal-header">
          <h3>📥 配置读取点位</h3>
          <button type="button" class="secondary-button small-button" @click="closeInputPointModal">关闭</button>
        </div>
        <div class="modal-body">
          <div class="binding-basic-grid compact-grid">
            <label>
              <span>绑定模式</span>
              <select v-model="activeInputBinding.binding_type" @change="switchInputBindingType(activeInputBinding, activeInputBinding.binding_type)">
                <option value="single">单点</option>
                <option value="batch">批量</option>
                <option value="history">TDEngine 历史窗口</option>
              </select>
            </label>
            <label>
              <span>插件输入名</span>
              <select v-if="manifestInputDefs.length > 0" v-model="activeInputBinding.input_name" @change="onInputBindingNameChange(activeInputBinding)">
                <option :value="''">{{ activeInputBinding.binding_type === 'batch' ? '按 manifest 输入列表逐项映射' : '请选择 manifest 输入' }}</option>
                <option v-for="item in manifestInputDefs" :key="item.name" :value="item.name">
                  {{ item.required ? `${item.name} *` : item.name }}
                </option>
              </select>
              <input v-else v-model="activeInputBinding.input_name" placeholder="如 value、inputs" />
            </label>
            <label>
              <span>数据源</span>
              <select v-model="activeInputBinding.data_source_id" @change="onInputBindingDataSourceChange(activeInputBinding)">
                <option value="">请选择数据源</option>
                <option
                  v-for="source in dataSources"
                  :key="source.id"
                  :value="String(source.id)"
                  :disabled="!dataSourceAllowedForInputBinding(activeInputBinding, source)"
                >
                  {{ source.name }} · {{ source.connector_type }}
                </option>
              </select>
            </label>
          </div>

          <template v-if="activeInputBinding.binding_type === 'single'">
            <div class="binding-single-grid">
              <label>
                <span>位点选择</span>
                <select v-model="activeInputBinding.source_tag">
                  <option value="">请选择可读位点</option>
                  <option v-for="point in inputOptions(activeInputBinding)" :key="point.tag" :value="point.tag">
                    {{ point.label }}
                  </option>
                </select>
              </label>
              <label>
                <span>手动 Redis Key / 位点</span>
                <input v-model="activeInputBinding.source_tag" placeholder="如 sthb:DCS_AO_RTO_014_AI" />
              </label>
            </div>
          </template>

          <template v-else-if="activeInputBinding.binding_type === 'history'">
            <div class="binding-basic-grid compact-grid">
              <div class="binding-actions-inline inline-fill">
                <button type="button" class="secondary-button" @click="selectAllInputTags(activeInputBinding)">全选位点</button>
                <button type="button" class="secondary-button" @click="clearAllInputTags(activeInputBinding)">清空</button>
                <span class="muted">已选 {{ activeInputBinding.source_tags.length }} 个历史位点</span>
              </div>
            </div>

            <div v-if="hasManifestHistoryTags(activeInputBinding)" class="manifest-history-panel">
              <div class="manifest-history-title">manifest 声明历史位点</div>
              <div class="manifest-history-tags">
                <span v-for="tag in historyTagsFromManifest(activeInputBinding)" :key="tag" class="manifest-history-tag">{{ tag }}</span>
              </div>
              <button type="button" class="secondary-button small-button" @click="applyManifestHistoryTags(activeInputBinding)">使用 manifest 位点</button>
            </div>

            <div v-if="inputOptions(activeInputBinding).length > 0" class="point-picker-grid">
              <label v-for="point in inputOptions(activeInputBinding)" :key="point.tag" class="point-check checkbox-box">
                <input
                  type="checkbox"
                  :checked="activeInputBinding.source_tags.includes(point.tag)"
                  @change="updateInputTagSelection(activeInputBinding, point.tag, ($event.target as HTMLInputElement).checked)"
                />
                <span>{{ point.label }}</span>
              </label>
            </div>
            <div v-else class="empty-inline">当前 TDEngine 数据源未配置可读位点。</div>

            <div class="history-window-grid">
              <label>
                <span>起点：当前时间前 N 分钟</span>
                <input v-model.number="activeInputBinding.window.start_offset_min" type="number" min="1" step="1" />
              </label>
              <label>
                <span>终点：当前时间前 N 分钟</span>
                <input v-model.number="activeInputBinding.window.end_offset_min" type="number" min="0" step="1" />
              </label>
              <label>
                <span>点间隔（秒）</span>
                <input v-model.number="activeInputBinding.window.sample_interval_sec" type="number" min="1" step="1" />
              </label>
              <label>
                <span>首值回溯（秒）</span>
                <input v-model.number="activeInputBinding.window.lookback_before_start_sec" type="number" min="0" step="1" />
              </label>
              <label>
                <span>缺失值策略</span>
                <select v-model="activeInputBinding.window.fill_method">
                  <option value="ffill_then_interpolate">前向填充 + 时间插值</option>
                  <option value="ffill">仅前向填充</option>
                  <option value="interpolate">仅时间插值</option>
                  <option value="none">保留空值</option>
                </select>
              </label>
              <label class="checkbox-box history-checkbox">
                <input v-model="activeInputBinding.window.strict_first_value" type="checkbox" />
                <span>首行仍缺值时阻止运行</span>
              </label>
            </div>
            <p class="muted history-note">起点偏移必须大于终点偏移。例如起点 60、终点 0 表示读取最近 60 分钟至当前时间的数据。</p>
          </template>

          <template v-else>
            <div class="binding-basic-grid compact-grid">
              <label>
                <span>批量输出格式</span>
                <select v-model="activeInputBinding.output_format" @change="onInputBindingOutputFormatChange(activeInputBinding)">
                  <option value="named-map">named-map (键值对)</option>
                  <option value="ordered-list">ordered-list (有序列表)</option>
                </select>
              </label>
              <div v-if="isManifestBatchBinding(activeInputBinding)" class="binding-actions-inline inline-fill">
                <button type="button" class="secondary-button" @click="clearManifestInputMappings(activeInputBinding)">清空映射</button>
                <span class="muted">按 manifest 输入名逐项选择 Redis 位点</span>
              </div>
              <div v-else class="binding-actions-inline inline-fill">
                <button type="button" class="secondary-button" @click="selectAllInputTags(activeInputBinding)">全选位点</button>
                <button type="button" class="secondary-button" @click="clearAllInputTags(activeInputBinding)">清空</button>
                <span class="muted">已选 {{ activeInputBinding.source_tags.length }} 个</span>
              </div>
            </div>

            <template v-if="isManifestBatchBinding(activeInputBinding)">
              <div class="mapping-table">
                <div class="mapping-head">
                  <strong>批量映射目标</strong>
                  <span class="muted">左侧为 manifest 输入名；右侧选择对应 Redis 位点</span>
                </div>
                <div v-for="item in activeInputBinding.source_mappings" :key="item.key" class="mapping-row manifest-target-row">
                  <div class="mapping-target">
                    <span class="mapping-key">{{ item.key }}</span>
                    <span v-if="isRequiredInputName(item.key)" class="required-badge">必填</span>
                  </div>
                  <div class="mapping-target-inputs">
                    <select :value="item.tag" @change="updateManifestMappingTag(activeInputBinding, item.key, ($event.target as HTMLSelectElement).value)">
                      <option value="">请选择可读位点</option>
                      <option v-for="point in inputOptions(activeInputBinding)" :key="point.tag" :value="point.tag">
                        {{ point.label }}
                      </option>
                    </select>
                    <input :value="item.tag" @input="updateManifestMappingTag(activeInputBinding, item.key, ($event.target as HTMLInputElement).value)" placeholder="如 sthb:DCS..." />
                  </div>
                </div>
              </div>
            </template>

            <template v-else>
              <div v-if="inputOptions(activeInputBinding).length > 0" class="point-picker-grid">
                <label v-for="point in inputOptions(activeInputBinding)" :key="point.tag" class="point-check checkbox-box">
                  <input
                    type="checkbox"
                    :checked="activeInputBinding.source_tags.includes(point.tag)"
                    @change="updateInputTagSelection(activeInputBinding, point.tag, ($event.target as HTMLInputElement).checked)"
                  />
                  <span>{{ point.label }}</span>
                </label>
              </div>
              <div v-else class="empty-inline">当前数据源未配置可读位点。</div>

              <div v-if="activeInputBinding.output_format === 'named-map' && activeInputBinding.source_mappings.length > 0" class="mapping-table">
                <div class="mapping-head">
                  <strong>named-map 映射</strong>
                  <span class="muted">右侧键名将作为插件读取时的对应 Key</span>
                </div>
                <div v-for="item in activeInputBinding.source_mappings" :key="item.tag" class="mapping-row">
                  <div class="mapping-tag">{{ item.tag }}</div>
                  <input class="mapping-input" :value="item.key" @input="updateMappingKey(activeInputBinding, item.tag, ($event.target as HTMLInputElement).value)" placeholder="如 input_014" />
                </div>
              </div>

              <div v-if="activeInputBinding.output_format === 'ordered-list' && activeInputBinding.source_tags.length > 0" class="mapping-table">
                <div class="mapping-head">
                  <strong>ordered-list 顺序</strong>
                  <span class="muted">插件收到的列表值将严格按这里的顺序排列</span>
                </div>
                <div v-for="(tag, orderIndex) in activeInputBinding.source_tags" :key="tag" class="mapping-row order-row">
                  <div class="mapping-tag">#{{ orderIndex + 1 }} · {{ tag }}</div>
                  <div class="order-actions">
                    <button type="button" class="secondary-button small-button" @click="moveInputTag(activeInputBinding, orderIndex, -1)">⬆ 上移</button>
                    <button type="button" class="secondary-button small-button" @click="moveInputTag(activeInputBinding, orderIndex, 1)">⬇ 下移</button>
                  </div>
                </div>
              </div>
            </template>
          </template>
        </div>
      </div>
    </div>
    </Transition>

    <Transition name="modal-fade" appear>
    <div v-if="activeOutputBinding" class="modal-mask" @click.self="closeOutputPointModal">
      <div class="modal-shell point-modal-shell">
        <div class="modal-header">
          <h3>📤 配置回写点位</h3>
          <button type="button" class="secondary-button small-button" @click="closeOutputPointModal">关闭</button>
        </div>
        <div class="modal-body">
          <div class="binding-basic-grid compact-grid">
            <label>
              <span>绑定模式</span>
              <select v-model="activeOutputBinding.binding_type" @change="switchOutputBindingType(activeOutputBinding, activeOutputBinding.binding_type)">
                <option value="single">单点</option>
                <option value="batch">批量</option>
              </select>
            </label>
            <label>
              <span>插件输出名</span>
              <select v-if="manifestOutputDefs.length > 0" v-model="activeOutputBinding.output_name">
                <option value="">请选择 manifest 输出</option>
                <option v-for="item in manifestOutputDefs" :key="item.name" :value="item.name">
                  {{ item.name }}
                </option>
              </select>
              <input v-else v-model="activeOutputBinding.output_name" placeholder="如 output_020" />
            </label>
            <label>
              <span>数据源</span>
              <select v-model="activeOutputBinding.data_source_id" @change="activeOutputBinding.target_tag = ''; activeOutputBinding.target_tags = []">
                <option value="">请选择数据源</option>
                <option v-for="source in dataSources" :key="source.id" :value="String(source.id)">
                  {{ source.name }}
                </option>
              </select>
            </label>
            <label class="checkbox-box dryrun-box">
              <input v-model="activeOutputBinding.dry_run" type="checkbox" />
              <span>Dry-run (阻断写)</span>
            </label>
          </div>

          <template v-if="activeOutputBinding.binding_type === 'single'">
            <div class="binding-single-grid">
              <label>
                <span>位点选择</span>
                <select v-model="activeOutputBinding.target_tag">
                  <option value="">请选择可写位点</option>
                  <option v-for="point in outputOptions(activeOutputBinding)" :key="point.tag" :value="point.tag">
                    {{ point.label }}
                  </option>
                </select>
              </label>
              <label>
                <span>手动 Redis Key / 位点</span>
                <input v-model="activeOutputBinding.target_tag" placeholder="如 sthb:DCS_AO_RTO_020_AI" />
              </label>
            </div>
          </template>

          <template v-else>
            <div class="binding-actions-inline inline-fill">
              <button type="button" class="secondary-button" @click="selectAllOutputTags(activeOutputBinding)">全选位点</button>
              <button type="button" class="secondary-button" @click="clearAllOutputTags(activeOutputBinding)">清空</button>
              <span class="muted">已选 {{ activeOutputBinding.target_tags.length }} 个</span>
            </div>
            <div class="muted small-note">批量回写时，插件输出应返回对象，键名直接使用目标位点名。</div>
            <div v-if="outputOptions(activeOutputBinding).length > 0" class="point-picker-grid">
              <label v-for="point in outputOptions(activeOutputBinding)" :key="point.tag" class="point-check checkbox-box">
                <input
                  type="checkbox"
                  :checked="activeOutputBinding.target_tags.includes(point.tag)"
                  @change="activeOutputBinding.target_tags = (($event.target as HTMLInputElement).checked ? [...new Set([...activeOutputBinding.target_tags, point.tag])] : activeOutputBinding.target_tags.filter((tag) => tag !== point.tag))"
                />
                <span>{{ point.label }}</span>
              </label>
            </div>
            <div v-else class="empty-inline">当前数据源未配置可写位点。</div>
          </template>
        </div>
      </div>
    </div>
    </Transition>
  </section>
</template>

<style scoped>
/* ==========================================
   1. 设计令牌 (Design Tokens) - 赛博/深色工业风
   ========================================== */
.instances-page {
  --color-primary: #00e5ff; /* 青色/Cyan */
  --color-primary-hover: #00b8d4;
  --color-success: #00e676; /* 亮绿 */
  --color-warning: #ffb300; /* 亮黄 */
  --color-danger: #ff4d4f;  /* 亮红 */
  
  --color-bg-base: #020914; /* 页面底色，极深的星空蓝 */
  --color-bg-surface: rgba(4, 18, 36, 0.8); /* 面板背景 */
  --color-bg-subtle: rgba(13, 34, 56, 0.6);
  --color-bg-muted: rgba(255, 255, 255, 0.05);

  --color-border: rgba(0, 229, 255, 0.2);
  --color-border-hover: rgba(0, 229, 255, 0.5);
  --color-border-focus: #00e5ff;

  --color-text-main: #e2e8f0;
  --color-text-muted: #8ba1b5;
  --color-text-light: #567391;

  --radius-sm: 2px;
  --radius-md: 2px;
  --radius-lg: 4px;
  --radius-xl: 4px; /* 去除原有的大圆角设定 */

  --shadow-sm: none;
  --shadow-md: 0 4px 10px rgba(0, 0, 0, 0.5);
  --shadow-lg: 0 8px 20px rgba(0, 0, 0, 0.6);
  --shadow-focus: 0 0 8px rgba(0, 229, 255, 0.5);

  --transition-all: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);

  width: 100%;
  min-height: 100vh;
  box-sizing: border-box;
  padding: 24px 12px;
  margin: 0 auto;
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  color: var(--color-text-main);
  
  /* 全局科技网格背景 */
  background-color: var(--color-bg-base);
  background-image: 
    linear-gradient(rgba(0, 229, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 229, 255, 0.03) 1px, transparent 1px);
  background-size: 30px 30px;
}

/* 全局滚动条美化 */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.3);
}
::-webkit-scrollbar-thumb {
  background: rgba(0, 229, 255, 0.2);
  border-radius: var(--radius-sm);
}
::-webkit-scrollbar-thumb:hover {
  background: var(--color-primary);
}

/* ==========================================
   2. 页面布局与头部 (Page & Header)
   ========================================== */
.page-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 32px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--color-border);
  position: relative;
}
.page-heading::after {
  content: "";
  position: absolute;
  bottom: -1px;
  left: 0;
  width: 120px;
  height: 2px;
  background: var(--color-primary);
  box-shadow: 0 0 8px var(--color-primary);
}
.heading-text { display: flex; flex-direction: column; gap: 4px; }
.eyebrow {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--color-primary);
}
.page-heading h2 {
  margin: 0;
  font-size: 28px;
  font-weight: 800;
  letter-spacing: 1px;
  color: #fff;
  text-shadow: 0 0 10px rgba(0, 229, 255, 0.4);
}
.subtitle {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-muted);
}
.header-actions { display: flex; gap: 12px; }

/* ==========================================
   3. 交互组件体系 (Buttons & Inputs)
   ========================================== */
button {
  font-family: inherit;
  transition: var(--transition-all);
}
.primary-button, .secondary-button, .danger-button, .btn-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 18px;
  border-radius: var(--radius-sm);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  outline: none;
  border: 1px solid transparent;
  white-space: nowrap;
}
.primary-button {
  background: transparent;
  color: var(--color-primary);
  border-color: var(--color-primary);
  box-shadow: inset 0 0 10px rgba(0, 229, 255, 0.2);
}
.primary-button:hover:not(:disabled) {
  background: rgba(0, 229, 255, 0.2);
  box-shadow: inset 0 0 15px rgba(0, 229, 255, 0.4);
  transform: translateY(-1px);
}
.secondary-button {
  background: rgba(255, 255, 255, 0.05);
  border-color: var(--color-border);
  color: var(--color-text-main);
}
.secondary-button:hover:not(:disabled) {
  background: rgba(0, 229, 255, 0.1);
  border-color: var(--color-primary);
  color: var(--color-primary);
}
.danger-button {
  background: rgba(255, 77, 79, 0.1);
  border-color: rgba(255, 77, 79, 0.5);
  color: var(--color-danger);
}
.danger-button:hover:not(:disabled) {
  background: rgba(255, 77, 79, 0.2);
  border-color: var(--color-danger);
}
.btn-icon {
  padding: 8px 12px;
  background: transparent;
  border-color: rgba(255, 255, 255, 0.1);
  color: var(--color-text-muted);
  flex: 1;
}
.btn-icon:hover:not(:disabled) {
  background: rgba(0, 229, 255, 0.1);
  color: var(--color-primary);
  border-color: var(--color-primary);
}
.small-button {
  padding: 6px 12px;
  font-size: 13px;
}
button:focus-visible { box-shadow: var(--shadow-focus); }
button:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

/* 表单输入与网格结构 */
label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-main);
}
input, select, textarea {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: rgba(0, 0, 0, 0.5);
  font-size: 14px;
  color: #fff;
  transition: var(--transition-all);
  box-sizing: border-box;
  color-scheme: dark;
}
input:hover, select:hover, textarea:hover {
  border-color: var(--color-border-hover);
}
input:focus, select:focus, textarea:focus {
  outline: none;
  border-color: var(--color-border-focus);
  box-shadow: inset 0 0 5px rgba(0, 229, 255, 0.3);
}
input:disabled, select:disabled {
  background: rgba(255,255,255,0.05);
  color: var(--color-text-muted);
  cursor: not-allowed;
}
textarea { font-family: ui-monospace, monospace; resize: vertical; }

.checkbox-box {
  flex-direction: row;
  align-items: center;
  padding: 12px 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  background: rgba(0, 0, 0, 0.3);
  transition: var(--transition-all);
}
.checkbox-box:hover {
  border-color: var(--color-border-focus);
  background: rgba(0, 229, 255, 0.05);
}
.checkbox-box input[type="checkbox"] {
  width: 18px;
  height: 18px;
  margin: 0;
  accent-color: var(--color-primary);
}

/* ==========================================
   4. 列表与卡片视图 (Cards & States)
   ========================================== */
.empty-state, .empty-inline {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 60px 20px;
  background: rgba(0, 0, 0, 0.3);
  border: 1px dashed rgba(0, 229, 255, 0.3);
  border-radius: var(--radius-lg);
  color: var(--color-text-muted);
  font-size: 15px;
}
.empty-inline { padding: 32px 20px; font-size: 14px; }
.error-banner {
  background: rgba(255, 77, 79, 0.1);
  border: 1px solid #ff4d4f;
  color: #ff4d4f;
  padding: 14px 16px;
  border-radius: var(--radius-md);
  margin-bottom: 24px;
  font-weight: 600;
  box-shadow: 0 0 10px rgba(255, 77, 79, 0.2);
}

.instances-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 24px;
}

/* 核心的科技感面板基类 */
.instance-card,
.modal-shell,
.form-panel,
.binding-list-card,
.binding-summary-card,
.mapping-table,
.manifest-block {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  position: relative;
}

/* 面板边角修饰装饰 */
.instance-card::before,
.modal-shell::before,
.form-panel::before,
.binding-list-card::before,
.binding-summary-card::before {
  content: "";
  position: absolute;
  top: -1px;
  left: -1px;
  width: 12px;
  height: 12px;
  border-top: 2px solid var(--color-primary);
  border-left: 2px solid var(--color-primary);
  pointer-events: none;
}
.instance-card::after,
.modal-shell::after,
.form-panel::after,
.binding-list-card::after,
.binding-summary-card::after {
  content: "";
  position: absolute;
  bottom: -1px;
  right: -1px;
  width: 12px;
  height: 12px;
  border-bottom: 2px solid var(--color-primary);
  border-right: 2px solid var(--color-primary);
  pointer-events: none;
}

.instance-card {
  padding: 24px;
  display: flex;
  flex-direction: column;
  transition: var(--transition-all);
}
.instance-card:hover {
  border-color: var(--color-primary);
  box-shadow: 0 0 15px rgba(0, 229, 255, 0.2);
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 12px;
}
.card-title-wrap h3 {
  margin: 0 0 8px 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--color-primary);
  text-shadow: 0 0 5px rgba(0, 229, 255, 0.3);
  line-height: 1.2;
}
.version-badge {
  display: inline-block;
  background: rgba(255, 255, 255, 0.05);
  color: var(--color-text-main);
  padding: 4px 10px;
  border-radius: 2px;
  font-size: 12px;
  font-weight: 600;
  border: 1px solid rgba(255, 255, 255, 0.1);
}
.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 700;
  color: var(--color-text-main);
  text-transform: uppercase;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.1);
  padding: 6px 12px;
  border-radius: 2px;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-text-light);
}
.status-dot.running { background: var(--color-success); box-shadow: 0 0 8px var(--color-success); }
.status-dot.stopped { background: var(--color-danger); box-shadow: 0 0 8px var(--color-danger); }
.status-dot.error { background: var(--color-warning); box-shadow: 0 0 8px var(--color-warning); }

.card-body { flex-grow: 1; }
.info-row {
  display: flex;
  justify-content: space-between;
  font-size: 14px;
  margin-bottom: 12px;
  color: var(--color-text-muted);
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  padding-bottom: 8px;
}
.info-label { font-weight: 500; }
.info-value { font-weight: 600; color: var(--color-text-main); }
.text-danger { color: var(--color-danger) !important; }
.text-warning { color: var(--color-warning) !important; }
.text-success { color: var(--color-success) !important; }

.schedule-times {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.05);
  padding: 16px;
  border-radius: var(--radius-md);
  margin-top: 20px;
}
.time-box { display: flex; flex-direction: column; gap: 4px; }
.time-label { font-size: 12px; color: var(--color-text-muted); }
.time-val { font-size: 13px; font-weight: 700; color: #fff; }

.card-actions-bar {
  display: flex;
  gap: 12px;
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid var(--color-border);
}

/* 运行历史 */
.run-history-expander {
  margin-top: 16px;
  background: rgba(0, 0, 0, 0.3);
  border-radius: var(--radius-md);
  padding: 12px 16px;
  border: 1px solid var(--color-border);
}
.run-history-expander summary {
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-primary);
  outline: none;
  user-select: none;
}
.run-history-content {
  margin-top: 16px;
  border-top: 1px dashed var(--color-border);
  padding-top: 16px;
}
.history-item {
  border-left: 2px solid var(--color-border-hover);
  padding-left: 14px;
  margin-bottom: 16px;
}
.history-item-head {
  display: flex;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
}
.run-type { color: var(--color-primary); }
.run-time { color: var(--color-text-light); font-weight: 400; font-size: 12px; }
.run-logs, .manual-run-result pre {
  margin: 0;
  background: rgba(0, 0, 0, 0.6);
  color: var(--color-success); /* 终端绿 */
  border: 1px solid rgba(255,255,255,0.1);
  padding: 12px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  overflow-x: auto;
  max-height: 200px;
  font-family: ui-monospace, monospace;
}
.manual-run-result {
  margin-top: 16px;
  padding: 0;
}
.result-title { margin: 0 0 10px 0; font-weight: 600; color: var(--color-primary); }

/* ==========================================
   5. 弹窗系统 (Modals)
   ========================================== */
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.8);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  z-index: 2000;
}
.modal-shell {
  box-shadow: 0 0 30px rgba(0, 229, 255, 0.15);
  display: flex;
  flex-direction: column;
  width: min(1120px, 100%);
  max-height: calc(100vh - 48px);
}
.instance-modal-shell { width: min(1180px, 100%); }
.binding-modal-shell { width: min(1040px, 100%); }
.point-modal-shell { width: min(1080px, 100%); }

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 32px;
  border-bottom: 1px solid var(--color-border);
  background: rgba(4, 18, 36, 0.95);
}
.modal-header h3 { margin: 0; font-size: 18px; font-weight: 700; color: var(--color-primary); }
.modal-body { padding: 32px; overflow-y: auto; background: rgba(2, 9, 20, 0.95); }
.modal-footer {
  padding: 20px 32px;
  border-top: 1px solid var(--color-border);
  background: rgba(4, 18, 36, 0.95);
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

/* ==========================================
   6. 复杂表单、网格与列表区域 (Forms & Grids)
   ========================================== */
.form-panel {
  padding: 24px;
  margin-bottom: 24px;
}
.panel-title {
  margin: 0 0 24px 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--color-primary);
}
.instance-form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 24px; }
.schedule-picker { display: flex; flex-direction: column; gap: 8px; }
.schedule-picker-title { font-size: 14px; font-weight: 600; }
.schedule-select-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.schedule-select-row label { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 8px; }
.schedule-note { margin: 0; }

.binding-summary-panel { display: grid; gap: 16px; background: transparent; border: none; padding: 0;}
.binding-summary-card {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 24px;
}
.binding-summary-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.summary-pill {
  display: inline-flex;
  align-items: center;
  padding: 6px 12px;
  border-radius: 2px;
  background: rgba(0, 0, 0, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.1);
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-main);
}

.binding-list-modal-body { display: grid; gap: 20px; }
.binding-list-card {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 24px;
}
.binding-head { display: flex; align-items: center; justify-content: space-between; }
.binding-title-line { display: flex; align-items: center; gap: 12px; font-size: 16px; font-weight: 700; color: var(--color-primary); }
.binding-list-actions { display: flex; gap: 12px; }
.binding-basic-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 20px; }
.binding-single-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.manifest-history-panel { margin-top: 16px; padding: 14px; border: 1px solid rgba(0, 229, 255, 0.3); border-radius: var(--radius-md); background: rgba(0, 229, 255, 0.05); display: grid; gap: 10px; }
.manifest-history-title { font-weight: 700; color: var(--color-primary); }
.manifest-history-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.manifest-history-tag { padding: 4px 10px; border-radius: 2px; background: rgba(0, 229, 255, 0.1); color: var(--color-primary); font-size: 12px; border: 1px solid rgba(0, 229, 255, 0.3); }
.history-window-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; margin-top: 20px; }
.history-checkbox { align-self: end; min-height: 40px; }
.history-note { margin-top: 12px; }
.compact-grid { align-items: end; }
.inline-fill { grid-column: 1 / -1; }
.binding-actions-inline { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.summary-box {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
  padding: 10px 14px;
  border: 1px solid rgba(0, 229, 255, 0.5);
  border-radius: var(--radius-sm);
  background: rgba(0, 229, 255, 0.05);
}

/* 映射规则与列表项 */
.mapping-table, .manifest-block {
  overflow: hidden;
}
.mapping-head, .manifest-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 20px;
  background: rgba(0, 229, 255, 0.1);
  color: var(--color-primary);
  border-bottom: 1px solid var(--color-border);
  font-size: 14px;
}
.mapping-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(240px, 0.9fr);
  gap: 16px;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  align-items: center;
}
.mapping-row:last-child { border-bottom: none; }
.manifest-target-row { grid-template-columns: minmax(220px, 0.8fr) minmax(0, 1.4fr); }
.order-row { grid-template-columns: minmax(0, 1fr) auto; }
.mapping-tag, .mapping-target {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: rgba(0, 0, 0, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: var(--radius-sm);
  font-family: ui-monospace, monospace;
  font-size: 13px;
  color: #fff;
}
.mapping-target-inputs { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

/* 规范展示 (Manifest) */
.manifest-summary { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
.manifest-chip-grid { display: flex; flex-wrap: wrap; gap: 10px; padding: 16px 20px; }
.manifest-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 2px;
  font-size: 13px;
  font-weight: 600;
  background: rgba(0, 0, 0, 0.3);
}
.manifest-chip small { color: var(--color-text-muted); font-weight: 400; }
.manifest-chip.required {
  border-color: #ff4d4f;
  background: rgba(255, 77, 79, 0.1);
  color: #ff4d4f;
}
.required-badge {
  padding: 2px 8px;
  border-radius: 2px;
  background: #ff4d4f;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}
.error-inline { margin: 12px 20px 20px; color: var(--color-danger); font-size: 13px; font-weight: 600; }

.point-picker-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}
.dryrun-box { margin-top: 16px; width: fit-content; }
.small-note, .muted { font-size: 13px; color: var(--color-text-muted); }

/* ==========================================
   7. 动画与过渡 (Transitions)
   ========================================== */
.modal-fade-enter-active, .modal-fade-leave-active {
  transition: opacity 0.25s ease, backdrop-filter 0.25s ease;
}
.modal-fade-enter-from, .modal-fade-leave-to {
  opacity: 0;
  backdrop-filter: blur(0px);
}
.modal-fade-enter-active .modal-shell {
  animation: modal-slide-up 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}
.modal-fade-leave-active .modal-shell {
  animation: modal-slide-down 0.2s cubic-bezier(0.4, 0, 1, 1) forwards;
}

@media (max-width: 768px) {
  .instances-page{
    padding: 16px 8px;
  }
}

@keyframes modal-slide-up {
  from { opacity: 0; transform: translateY(24px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes modal-slide-down {
  from { opacity: 1; transform: translateY(0) scale(1); }
  to { opacity: 0; transform: translateY(12px) scale(0.98); }
}

@media (max-width: 1024px) {
  .instance-form-grid, .binding-basic-grid, .binding-single-grid, .history-window-grid, .manifest-summary, .compact-grid { grid-template-columns: 1fr; gap: 16px; }
  .mapping-row { grid-template-columns: 1fr; }
  .schedule-select-row { grid-template-columns: 1fr; }
  .binding-summary-card { flex-direction: column; }
  .instances-grid { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  .modal-mask { padding: 12px; }
  .modal-shell { max-height: calc(100vh - 24px); }
  .modal-header, .modal-footer { padding: 16px 20px; }
  .modal-body { padding: 20px; }
  .card-header { flex-direction: column; align-items: flex-start; gap: 12px; }
}
</style>