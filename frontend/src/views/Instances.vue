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

type BindingType = 'single' | 'batch'
type BatchOutputFormat = 'named-map' | 'ordered-list'

interface ManifestInterfaceDef {
  name: string
  type: string
  required: boolean
  description: string
}

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

// === 视图状态控制 ===
const isFormVisible = ref(false)

function showCreateForm() {
  resetForm()
  isFormVisible.value = true
}

function cancelForm() {
  resetForm()
  isFormVisible.value = false
}
// ====================

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
  pluginVersions.value = packageName ? await listPackageVersions(packageName) :[]
}

async function applyDefaultPlugin() {
  const currentPackage = pluginPackages.value.find((item) => item.name === form.value.package_name)
  const selectedPackage = currentPackage ?? pluginPackages.value[0]
  if (!selectedPackage) {
    form.value.package_name = ''
    form.value.version = ''
    pluginVersions.value =[]
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
  return {
    binding_type: 'single',
    input_name: inputName,
    data_source_id: dataSources.value[0] ? String(dataSources.value[0].id) : '',
    source_tag: '',
    source_tags: [],
    source_mappings:[],
    output_format: 'named-map',
  }
}

function defaultOutputBinding(outputName = ''): OutputBindingRow {
  return {
    binding_type: 'single',
    output_name: outputName,
    data_source_id: dataSources.value[0] ? String(dataSources.value[0].id) : '',
    target_tag: '',
    target_tags:[],
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
  binding.source_mappings =[]
  if (type === 'batch') {
    binding.output_format = 'named-map'
    binding.input_name = ''
    syncManifestSourceMappings(binding)
  }
}

function switchOutputBindingType(binding: OutputBindingRow, type: BindingType) {
  binding.binding_type = type
  binding.target_tag = ''
  binding.target_tags =[]
}

function onInputBindingDataSourceChange(binding: InputBindingRow) {
  binding.source_tag = ''
  binding.source_tags =[]
  if (isManifestBatchBinding(binding)) {
    binding.source_mappings = binding.source_mappings.map((item) => ({ ...item, tag: '' }))
    return
  }
  binding.source_mappings =[]
}

function onInputBindingOutputFormatChange(binding: InputBindingRow) {
  binding.source_tag = ''
  binding.source_tags =[]
  if (binding.output_format === 'named-map' && !binding.input_name.trim()) {
    syncManifestSourceMappings(binding)
    return
  }
  binding.source_mappings =[]
}

function onBatchInputNameChange(binding: InputBindingRow) {
  if (binding.binding_type !== 'batch') return
  if (binding.output_format !== 'named-map') return
  binding.source_tag = ''
  binding.source_tags =[]
  if (!binding.input_name.trim()) {
    syncManifestSourceMappings(binding)
    return
  }
  binding.source_mappings =[]
}

function inputOptions(binding: InputBindingRow) {
  const source = findDataSource(binding.data_source_id)
  return source ? getReadPointOptions(source) :[]
}

function outputOptions(binding: OutputBindingRow) {
  const source = findDataSource(binding.data_source_id)
  return source ? getWritePointOptions(source) :[]
}

function sanitizePointKey(tag: string) {
  return tag.trim().replace(/[^A-Za-z0-9_]/g, '_')
}

function isManifestBatchBinding(binding: InputBindingRow) {
  return (
    binding.binding_type === 'batch' &&
    binding.output_format === 'named-map' &&
    !binding.input_name.trim() &&
    manifestInputDefs.value.length > 0
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
  const previous = new Map(binding.source_mappings.map((item) =>[item.tag, item.key]))
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
  binding.source_mappings =[]
}

function clearManifestInputMappings(binding: InputBindingRow) {
  binding.source_mappings = binding.source_mappings.map((item) => ({ ...item, tag: '' }))
  binding.source_tags =[]
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
  binding.target_tags =[]
}

function manifestInterfaces(kind: 'inputs' | 'outputs'): ManifestInterfaceDef[] {
  const manifest = selectedVersionRecord.value?.manifest
  if (!isRecord(manifest) || !isRecord(manifest.spec)) return []
  const raw = manifest.spec[kind]
  if (!Array.isArray(raw)) return[]
  return raw
    .filter((item): item is Record<string, unknown> => isRecord(item))
    .map((item) => ({
      name: stringValue(item.name).trim(),
      type: stringValue(item.type).trim(),
      required: Boolean(item.required),
      description: stringValue(item.description).trim(),
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
  const names: string[] =[]
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
        :[]
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

    const normalizedInputBindings = inputBindings.value
      .filter((binding) => binding.data_source_id && inputBindingHasPayload(binding))
      .map((binding) => {
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
      schedule_interval_sec: Number(form.value.schedule_interval_sec) || 30,
    })
    await loadAll()
    resetForm()
    isFormVisible.value = false // 保存成功后关闭表单
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
  ensureRequiredInputBindings()
  applyDefaultDataSource()
  isFormVisible.value = true // 编辑时展开表单
}

function normalizeSourceMappings(value: unknown, sourceTags: string[]) {
  const mappings = Array.isArray(value)
    ? value
        .filter((item): item is Record<string, unknown> => isRecord(item))
        .map((item) => ({ tag: stringValue(item.tag), key: stringValue(item.key) }))
        .filter((item) => item.tag || item.key)
    :[]
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
  outputBindings.value =[]
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
      .map((point) => pointOption(point, ['readTag', 'read_tag'],['canRead', 'can_read']))
      .filter((point): point is PointOption => Boolean(point))
    if (points.length > 0) return points
  }
  const configured = tagListFromConfig(source, 'readTags', 'read_tags')
  if (configured.length > 0) return configured.map((tag) => ({ label: tag, tag }))
  if (source.connector_type === 'mock' && isRecord(source.config.points)) {
    return Object.keys(source.config.points).map((tag) => ({ label: tag, tag }))
  }
  return[]
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
  return[]
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
  const pointClass = stringField(point,['class', 'pointClass', 'point_class']) || '未分类'
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
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') :[]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
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
      <div class="heading-text">
        <p class="eyebrow">Instances</p>
        <h2>运行实例管理</h2>
        <p class="subtitle">管理工业插件的运行实例。配置位点绑定、执行定时任务或手动触发实例运行。</p>
      </div>
      <div class="header-actions">
        <button type="button" class="secondary-button" @click="loadAll" :disabled="loading">
          {{ loading ? '↻ 刷新中...' : '↻ 刷新数据' }}
        </button>
        <button v-if="!isFormVisible" type="button" class="primary-button" @click="showCreateForm">
          + 创建新实例
        </button>
      </div>
    </div>

    <div v-if="error" class="error-banner">⚠️ {{ error }}</div>

    <!-- ================= 表单视图 (创建/编辑) ================= -->
    <div v-if="isFormVisible" class="form-view-container">
      <div class="form-view-header">
        <h3>{{ editingInstanceId ? '⚙️ 修改实例配置' : '✨ 创建新实例' }}</h3>
        <button type="button" class="secondary-button small-button" @click="cancelForm">返回列表</button>
      </div>

      <form class="config-form" @submit.prevent="submit">
        
        <!-- 区块 1：基础设置 -->
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
            <label>
              <span>定时间隔（秒）</span>
              <input v-model.number="form.schedule_interval_sec" type="number" min="5" step="1" required />
            </label>
            <label class="checkbox-box">
              <input v-model="form.schedule_enabled" type="checkbox" />
              <span>启用定时运行</span>
            </label>
            <label class="checkbox-box">
              <input v-model="form.writeback_enabled" type="checkbox" />
              <span :class="{'text-danger': form.writeback_enabled}">允许真实回写 (开启后将真实写入数据)</span>
            </label>
          </div>
        </div>

        <!-- 区块 2：Manifest摘要 -->
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
                ⚠️ 缺少必填输入绑定：{{ missingRequiredInputNames.join(', ') }}
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

        <!-- 区块 3：读取绑定 -->
        <div class="form-panel">
          <div class="panel-header">
            <h4 class="panel-title">📥 读取绑定 (Input Bindings)</h4>
            <button type="button" class="secondary-button" @click="addInputBinding">+ 新增读取绑定</button>
          </div>
          
          <div v-if="inputBindings.length === 0" class="empty-inline">暂无读取绑定，点击右侧按钮添加。</div>

          <div v-for="(binding, index) in inputBindings" :key="`in-${index}`" class="binding-card">
            <div class="binding-head">
              <div class="binding-title-line">
                <strong>绑定 #{{ index + 1 }}</strong>
                <span v-if="binding.input_name && isRequiredInputName(binding.input_name)" class="required-badge">必填</span>
              </div>
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
                <select v-if="manifestInputDefs.length > 0" v-model="binding.input_name" @change="onBatchInputNameChange(binding)">
                  <option :value="''">
                    {{ binding.binding_type === 'batch' ? '按 manifest 输入列表逐项映射' : '请选择 manifest 输入' }}
                  </option>
                  <option v-for="item in manifestInputDefs" :key="item.name" :value="item.name">
                    {{ item.required ? `${item.name} *` : item.name }}
                  </option>
                </select>
                <input v-else v-model="binding.input_name" placeholder="如 value、inputs" />
                <small v-if="binding.binding_type === 'batch' && binding.output_format === 'named-map'" class="muted small-note">
                  输入名留空时，将为每个 manifest 输入单独选择 Redis 位点。
                </small>
              </label>
              <label>
                <span>数据源</span>
                <select v-model="binding.data_source_id" @change="onInputBindingDataSourceChange(binding)">
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
                  <select v-model="binding.output_format" @change="onInputBindingOutputFormatChange(binding)">
                    <option value="named-map">named-map (键值对)</option>
                    <option value="ordered-list">ordered-list (有序列表)</option>
                  </select>
                </label>
                <div v-if="isManifestBatchBinding(binding)" class="binding-actions-inline">
                  <button type="button" class="secondary-button" @click="clearManifestInputMappings(binding)">清空映射</button>
                  <span class="muted">按 manifest 输入名逐项选择 Redis 位点</span>
                </div>
                <div v-else class="binding-actions-inline">
                  <button type="button" class="secondary-button" @click="selectAllInputTags(binding)">全选位点</button>
                  <button type="button" class="secondary-button" @click="clearAllInputTags(binding)">清空</button>
                  <span class="muted">已选 {{ binding.source_tags.length }} 个</span>
                </div>
              </div>

              <template v-if="isManifestBatchBinding(binding)">
                <div class="mapping-table">
                  <div class="mapping-head">
                    <strong>批量映射目标</strong>
                    <span class="muted">左侧为 manifest 输入名；右侧选择对应 Redis 位点</span>
                  </div>
                  <div v-for="item in binding.source_mappings" :key="item.key" class="mapping-row manifest-target-row">
                    <div class="mapping-target">
                      <span class="mapping-key">{{ item.key }}</span>
                      <span v-if="isRequiredInputName(item.key)" class="required-badge">必填</span>
                    </div>
                    <div class="mapping-target-inputs">
                      <select
                        :value="item.tag"
                        @change="updateManifestMappingTag(binding, item.key, ($event.target as HTMLSelectElement).value)"
                      >
                        <option value="">请选择可读位点</option>
                        <option v-for="point in inputOptions(binding)" :key="point.tag" :value="point.tag">
                          {{ point.label }}
                        </option>
                      </select>
                      <input
                        :value="item.tag"
                        @input="updateManifestMappingTag(binding, item.key, ($event.target as HTMLInputElement).value)"
                        placeholder="如 sthb:DCS..."
                      />
                    </div>
                  </div>
                </div>
              </template>

              <template v-else>
                <div v-if="inputOptions(binding).length > 0" class="point-picker-grid">
                  <label v-for="point in inputOptions(binding)" :key="point.tag" class="point-check checkbox-box">
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
                    <span class="muted">右侧键名将作为插件读取时的对应 Key</span>
                  </div>
                  <div v-for="item in binding.source_mappings" :key="item.tag" class="mapping-row">
                    <div class="mapping-tag">{{ item.tag }}</div>
                    <input class="mapping-input" :value="item.key" @input="updateMappingKey(binding, item.tag, ($event.target as HTMLInputElement).value)" placeholder="如 input_014" />
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
                      <button type="button" class="secondary-button small-button" @click="moveInputTag(binding, orderIndex, -1)">⬆ 上移</button>
                      <button type="button" class="secondary-button small-button" @click="moveInputTag(binding, orderIndex, 1)">⬇ 下移</button>
                    </div>
                  </div>
                </div>
              </template>
            </template>
          </div>
        </div>

        <!-- 区块 4：回写绑定 -->
        <div class="form-panel">
          <div class="panel-header">
            <h4 class="panel-title">📤 回写绑定 (Output Bindings)</h4>
            <button type="button" class="secondary-button" @click="addOutputBinding">+ 新增回写绑定</button>
          </div>

          <div v-if="outputBindings.length === 0" class="empty-inline">暂无回写绑定，点击右侧按钮添加。</div>

          <div v-for="(binding, index) in outputBindings" :key="`out-${index}`" class="binding-card">
            <div class="binding-head">
              <strong>绑定 #{{ index + 1 }}</strong>
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
                <select v-model="binding.data_source_id" @change="binding.target_tag = ''; binding.target_tags =[]">
                  <option value="">请选择数据源</option>
                  <option v-for="source in dataSources" :key="source.id" :value="String(source.id)">
                    {{ source.name }}
                  </option>
                </select>
              </label>
              <label class="checkbox-box" style="align-self: flex-end;">
                <input v-model="binding.dry_run" type="checkbox" />
                <span>Dry-run (阻断写)</span>
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
              <div class="muted small-note" style="margin-top:-6px;">批量回写时，插件输出应返回对象，键名直接使用目标位点名。</div>
              <div v-if="outputOptions(binding).length > 0" class="point-picker-grid">
                <label v-for="point in outputOptions(binding)" :key="point.tag" class="point-check checkbox-box">
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

        <!-- 区块 5：附加JSON配置 -->
        <div class="form-panel">
          <h4 class="panel-title">附加配置 (JSON)</h4>
          <label class="json-input wide-field">
            <textarea v-model="form.configText" rows="4" spellcheck="false" placeholder="在此输入自定义 JSON 配置..."></textarea>
          </label>
        </div>

        <!-- 表单操作按钮 -->
        <div class="form-actions-bar wide-field">
          <button type="button" class="secondary-button" @click="cancelForm">取消编辑</button>
          <button type="submit" class="primary-button" :disabled="saving">
            {{ saving ? '🔄 保存中...' : (editingInstanceId ? '💾 保存修改' : '✨ 确认创建') }}
          </button>
        </div>
      </form>
    </div>


    <!-- ================= 列表视图 (卡片流) ================= -->
    <div v-else class="list-view-container">
      <div v-if="instances.length === 0" class="empty-state">
        <p>暂无正在运行的实例 🍃</p>
        <button type="button" class="primary-button" @click="showCreateForm">+ 立即创建一个</button>
      </div>

      <div class="instances-grid">
        <div v-for="instance in instances" :key="instance.id" class="instance-card">
          <div class="card-header">
            <div class="card-title-wrap">
              <h3>{{ instance.name }}</h3>
              <span class="version-badge">{{ instance.package_name }} @ {{ instance.version }}</span>
            </div>
            <div class="status-indicator">
              <span class="status-dot" :class="{ 'running': instance.status === 'running', 'stopped': instance.status === 'stopped', 'error': instance.status === 'error' }"></span>
              {{ instance.status }}
            </div>
          </div>

          <div class="card-body">
            <div class="info-row">
              <span class="info-label">回写策略:</span>
              <span class="info-value" :class="{ 'text-danger': instance.writeback_enabled, 'text-success': !instance.writeback_enabled }">
                {{ instance.writeback_enabled ? '⚠️ 允许真实回写' : '🛡️ 仅 Dry-run' }}
              </span>
            </div>
            <div class="info-row">
              <span class="info-label">定时规则:</span>
              <span class="info-value">
                {{ instance.schedule_enabled ? `⏱ 每 ${instance.schedule_interval_sec} 秒` : '⏸ 未启用定时' }}
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
            <button type="button" class="btn-icon" title="修改" @click="editInstance(instance)">⚙️ 配置</button>
            <button type="button" class="btn-icon" title="手动运行" @click="run(instance)" :disabled="runningId === instance.id">
              {{ runningId === instance.id ? '⏳...' : '▶️ 运行' }}
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

          <!-- 折叠的运行历史，保持界面清爽 -->
          <details class="run-history-expander">
            <summary>查看最近运行记录 ({{ recentRunsForInstance(instance).length }})</summary>
            <div class="run-history-content">
              <div v-if="recentRunsForInstance(instance).length === 0" class="muted empty-history">
                暂无运行记录，定时触发后这里会自动刷新。
              </div>
              <div v-for="run in recentRunsForInstance(instance)" :key="run.run_id" class="history-item">
                <div class="history-item-head">
                  <span class="run-type">[{{ run.trigger_type }}]</span>
                  <span class="run-status" :class="run.status">{{ run.status }}</span>
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
    </div>
  </section>
</template>

<style scoped>
/* ================= 原有样式适配与保留 ================= */
.instances-page { max-width: 1360px; }
.binding-card { display: grid; gap: 12px; padding: 18px; border: 1px solid #d8e3df; border-radius: 8px; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.02); }
.binding-head, .binding-actions-inline, .manifest-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.binding-title-line { display: flex; align-items: center; gap: 8px; }
.binding-basic-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.binding-basic-grid label, .binding-single-grid label, .json-input { display: grid; gap: 8px; color: #2f403d; font-weight: 600; font-size: 14px; }
.binding-basic-grid input, .binding-basic-grid select, .binding-single-grid input, .binding-single-grid select, .mapping-input, .json-input textarea, .mapping-target-inputs input, .mapping-target-inputs select { width: 100%; padding: 10px; border: 1px solid #bacac5; border-radius: 6px; box-sizing: border-box; }
.binding-single-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.point-picker-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
.small-note, .muted { font-size: 13px; color: #7f8f8c; }
.empty-inline { padding: 16px; color: #5e6f6c; background: #f7faf9; border: 1px dashed #bacac5; border-radius: 6px; text-align: center; }
.mapping-table, .manifest-block { display: grid; gap: 10px; padding: 14px; border: 1px solid #d8e3df; border-radius: 8px; background: #fafcfb; }
.mapping-row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(220px, 0.9fr); gap: 12px; align-items: center; }
.mapping-tag { padding: 10px 12px; border: 1px solid #d8e3df; border-radius: 6px; background: #fff; overflow-wrap: anywhere; font-size: 14px;}
.mapping-target { display: flex; align-items: center; gap: 8px; padding: 10px 12px; border: 1px solid #d8e3df; border-radius: 6px; background: #fff; overflow-wrap: anywhere; }
.mapping-key { font-weight: 700; }
.mapping-target-inputs { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.manifest-target-row { grid-template-columns: minmax(220px, 0.8fr) minmax(0, 1.4fr); }
.order-row { grid-template-columns: minmax(0, 1fr) auto; }
.order-actions { display: flex; gap: 8px; }
.small-button { min-height: 34px; padding: 0 12px; font-size: 13px; }
.manifest-summary { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 12px;}
.manifest-chip-grid { display: flex; flex-wrap: wrap; gap: 8px; }
.manifest-chip { display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px; border: 1px solid #d8e3df; border-radius: 999px; background: #fff; font-size: 13px;}
.manifest-chip.required { border-color: #b65353; background: #fff5f5; color: #b65353; }
.required-badge { display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 999px; background: #b65353; color: #ffffff; font-size: 12px; font-weight: 700; }
.error-inline { margin: 8px 0 0 0; color: #b65353; font-size: 13px; font-weight: 700; }
pre { white-space: pre-wrap; word-break: break-word; font-family: monospace; }

/* ================= 升级的现代化 UI 样式 ================= */
.primary-button { background: #2f403d; color: #fff; border: none; padding: 10px 20px; border-radius: 6px; font-weight: 600; cursor: pointer; transition: background 0.2s; }
.primary-button:hover:not(:disabled) { background: #1f2d2b; }
.primary-button:disabled { opacity: 0.5; cursor: not-allowed; }
.header-actions { display: flex; gap: 12px; }

.error-banner { background-color: #fff5f5; border: 1px solid #b65353; color: #b65353; padding: 12px 16px; border-radius: 8px; font-weight: 600; margin-bottom: 24px; }

/* 表单布局重构 */
.form-view-container { background: #fff; border: 1px solid #d8e3df; border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 4px 16px rgba(0,0,0,0.04); }
.form-view-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; border-bottom: 1px solid #edf2f0; padding-bottom: 16px; }
.form-view-header h3 { margin: 0; color: #2f403d; font-size: 20px; }
.form-panel { margin-bottom: 24px; border: 1px solid #edf2f0; padding: 20px; border-radius: 8px; background: #fbfdfc; }
.panel-title { margin: 0 0 16px 0; font-size: 16px; color: #2f403d; font-weight: 700; }
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.panel-header h4 { margin: 0; }
.form-actions-bar { display: flex; justify-content: flex-end; gap: 16px; padding-top: 20px; border-top: 1px solid #edf2f0; margin-top: 32px;}
.instance-form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
.wide-field { grid-column: 1 / -1; }
.checkbox-box { display: flex; align-items: center; padding: 10px 16px; border: 1px solid #bacac5; border-radius: 6px; background: #fff; cursor: pointer; font-weight: 600; color: #2f403d; gap: 10px; transition: border 0.2s;}
.checkbox-box:hover { border-color: #2f403d; }
.checkbox-box input { width: 16px; height: 16px; margin:0;}

/* 卡片流列表 (List View) */
.empty-state { text-align: center; padding: 60px 20px; background: #fff; border: 1px dashed #bacac5; border-radius: 12px; color: #5e6f6c; font-size: 16px; }
.instances-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 20px; }
.instance-card { background: #fff; border: 1px solid #d8e3df; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.02); display: flex; flex-direction: column; transition: transform 0.2s, box-shadow 0.2s; }
.instance-card:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(0,0,0,0.06); border-color: #bacac5; }
.card-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.card-title-wrap h3 { margin: 0 0 8px 0; font-size: 18px; color: #2f403d; }
.version-badge { background: #e9f0ee; color: #4a5c59; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 700; }
.status-indicator { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; color: #5e6f6c; text-transform: uppercase;}
.status-dot { width: 10px; height: 10px; border-radius: 50%; background: #bacac5; }
.status-dot.running { background: #4caf50; box-shadow: 0 0 6px rgba(76, 175, 80, 0.4); }
.status-dot.stopped { background: #f44336; }
.status-dot.error { background: #b65353; }

.info-row { font-size: 14px; margin-bottom: 10px; color: #5e6f6c; display: flex; justify-content: space-between;}
.info-label { font-weight: 600; }
.info-value { font-weight: 600; color: #2f403d;}
.text-danger { color: #b65353 !important; }
.text-warning { color: #e6a23c !important; }
.text-success { color: #4caf50 !important; }

.schedule-times { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; background: #fbfdfc; padding: 14px; border: 1px solid #edf2f0; border-radius: 8px; margin-top: 16px; }
.time-box { display: flex; flex-direction: column; gap: 4px; }
.time-label { font-size: 12px; color: #7f8f8c; }
.time-val { font-size: 13px; font-weight: 700; color: #2f403d; }

.card-actions-bar { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 20px; padding-top: 16px; border-top: 1px solid #edf2f0; }
.btn-icon { background: #fff; border: 1px solid #d8e3df; padding: 8px 12px; border-radius: 6px; font-size: 13px; cursor: pointer; color: #4a5c59; font-weight: 600; transition: all 0.2s; flex: 1; text-align: center;}
.btn-icon:hover:not(:disabled) { background: #f5f8f7; border-color: #bacac5; }
.btn-icon:disabled { opacity: 0.5; cursor: not-allowed; }

.run-history-expander { margin-top: 16px; font-size: 13px; background: #fafcfb; border-radius: 8px; padding: 12px; border: 1px solid #edf2f0; }
.run-history-expander summary { cursor: pointer; color: #4a5c59; font-weight: 600; user-select: none; outline: none; }
.run-history-content { margin-top: 12px; border-top: 1px dashed #d8e3df; padding-top: 12px; }
.empty-history { text-align: center; padding: 10px; }
.history-item { border-left: 3px solid #bacac5; padding-left: 12px; margin-bottom: 12px; }
.history-item-head { display: flex; gap: 12px; margin-bottom: 6px; font-weight: 600; }
.run-type { color: #2f403d; }
.run-time { color: #7f8f8c; font-weight: 400; font-size: 12px; }
.run-logs { margin: 0; background: #2f403d; color: #e9f0ee; padding: 10px; border-radius: 6px; font-size: 12px; overflow-x: auto; max-height: 180px; }
.manual-run-result { margin-top: 16px; background: #fbfdfc; border: 1px solid #d8e3df; padding: 12px; border-radius: 8px; }
.result-title { margin: 0 0 8px 0; font-weight: 600; font-size: 13px; color: #2f403d; }

@media (max-width: 980px) {
  .instance-form-grid, .binding-basic-grid, .binding-single-grid, .point-picker-grid, .mapping-row, .order-row, .manifest-summary, .mapping-target-inputs, .manifest-target-row { grid-template-columns: 1fr; }
  .instances-grid { grid-template-columns: 1fr; }
}
</style>