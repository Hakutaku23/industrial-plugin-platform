<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import {
  deleteDataSource,
  listDataSources,
  saveDataSource,
  updateDataSource,
  type DataSourceRecord,
} from '../api/packages'

interface PointRow {
  pointClass: string
  readEnabled: boolean
  readTag: string
  writeEnabled: boolean
  writeTag: string
  mockValue: string
}

interface PointCatalogView {
  class?: string
  pointClass?: string
  readTag?: string
  read_tag?: string
  writeTag?: string
  write_tag?: string
  canRead?: boolean
  can_read?: boolean
  canWrite?: boolean
  can_write?: boolean
}

const dataSources = ref<DataSourceRecord[]>([])
const loading = ref(false)
const saving = ref(false)
const editingDataSourceId = ref<number | null>(null)
const error = ref('')
const form = ref(defaultForm())
const points = ref<PointRow[]>(defaultPoints())
const showForm = ref(false)

function defaultForm() {
  return {
    name: 'mock-line-a',
    connector_type: 'mock' as 'mock' | 'redis' | 'tdengine',
    host: '127.0.0.1',
    port: 6379,
    db: 0,
    redisPassword: '',
    keyPrefix: '',
    keySeparator: ':',
    tdengineUrl: 'http://127.0.0.1:6041',
    tdengineUser: 'root',
    tdenginePassword: '',
    tdengineDatabase: 'test',
    tdengineTableName: 'history',
    tdengineTimezone: 'Asia/Shanghai',
    read_enabled: true,
    write_enabled: true,
  }
}

function defaultPoints(): PointRow[] {
  return[
    {
      pointClass: 'demo',
      readEnabled: true,
      readTag: 'demo:value',
      writeEnabled: true,
      writeTag: 'demo:doubled',
      mockValue: '21',
    },
  ]
}

function resetForm() {
  editingDataSourceId.value = null
  form.value = defaultForm()
  points.value = defaultPoints()
  error.value = ''
  showForm.value = false
}

function handleCreate() {
  resetForm()
  showForm.value = true
}

function cancelEdit() {
  resetForm()
}

function isTdengineForm() {
  return form.value.connector_type === 'tdengine'
}

function supportsWriteBindings() {
  return form.value.connector_type !== 'tdengine'
}

function applyConnectorTypeRules() {
  if (isTdengineForm()) {
    form.value.read_enabled = true
    form.value.write_enabled = false
    for (const point of points.value) {
      point.writeEnabled = false
      point.writeTag = ''
    }
  }
}

watch(
  () => form.value.connector_type,
  () => {
    applyConnectorTypeRules()
  },
)

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

function addPoint() {
  points.value.push({
    pointClass: '',
    readEnabled: true,
    readTag: '',
    writeEnabled: false,
    writeTag: '',
    mockValue: '',
  })
  applyConnectorTypeRules()
}

function removePoint(index: number) {
  points.value.splice(index, 1)
}

function disableRead(point: PointRow) {
  if (!point.readEnabled) {
    point.readTag = ''
    point.mockValue = ''
  }
}

function disableWrite(point: PointRow) {
  if (!point.writeEnabled) {
    point.writeTag = ''
  }
}

function buildNormalizedPoints() {
  return points.value
    .map((point) => ({
      pointClass: point.pointClass.trim(),
      canRead: point.readEnabled,
      readTag: point.readEnabled ? point.readTag.trim() : '',
      canWrite: supportsWriteBindings() ? point.writeEnabled : false,
      writeTag: supportsWriteBindings() && point.writeEnabled ? point.writeTag.trim() : '',
      mockValue: point.readEnabled ? point.mockValue.trim() : '',
    }))
    .filter((point) => point.pointClass || point.readTag || point.writeTag)
}

function duplicateValues(values: string[]) {
  const seen = new Set<string>()
  const duplicates = new Set<string>()
  for (const value of values) {
    const normalized = value.trim()
    if (!normalized) continue
    if (seen.has(normalized)) duplicates.add(normalized)
    else seen.add(normalized)
  }
  return Array.from(duplicates)
}

function validateForm() {
  const name = form.value.name.trim()
  if (!name) throw new Error('请填写数据源名称')

  const duplicateSource = dataSources.value.find(
    (item) => item.name === name && item.id !== editingDataSourceId.value,
  )
  if (duplicateSource) {
    throw new Error(`数据源名称已存在: ${name}`)
  }

  if (form.value.connector_type === 'redis') {
    if (!form.value.host.trim()) throw new Error('请填写 Redis Host')
    if (!Number.isInteger(Number(form.value.port)) || Number(form.value.port) < 0) {
      throw new Error('Redis Port 必须为非负整数')
    }
    if (!Number.isInteger(Number(form.value.db)) || Number(form.value.db) < 0) {
      throw new Error('Redis DB 必须为非负整数')
    }
  }

  if (form.value.connector_type === 'tdengine') {
    if (!form.value.tdengineUrl.trim()) throw new Error('请填写 TDEngine URL')
    if (!form.value.tdengineDatabase.trim()) throw new Error('请填写 TDEngine 数据库名')
    if (!form.value.tdengineTableName.trim()) throw new Error('请填写 TDEngine 表名')
    form.value.read_enabled = true
    form.value.write_enabled = false
  }

  const normalizedPoints = buildNormalizedPoints()
  for (let index = 0; index < normalizedPoints.length; index += 1) {
    const point = normalizedPoints[index]
    if (point.canRead && !point.readTag) {
      throw new Error(`位点 #${index + 1} 已启用读取，但未填写读取标签`)
    }
    if (point.canWrite && !point.writeTag) {
      throw new Error(`位点 #${index + 1} 已启用回写，但未填写回写标签`)
    }
  }

  const duplicateReadTags = duplicateValues(
    normalizedPoints.filter((point) => point.canRead && point.readTag).map((point) => point.readTag),
  )
  if (duplicateReadTags.length > 0) {
    throw new Error(`读取标签重复: ${duplicateReadTags.join(', ')}`)
  }

  const duplicateWriteTags = duplicateValues(
    normalizedPoints.filter((point) => point.canWrite && point.writeTag).map((point) => point.writeTag),
  )
  if (duplicateWriteTags.length > 0) {
    throw new Error(`回写标签重复: ${duplicateWriteTags.join(', ')}`)
  }
}

function buildConfig() {
  const normalizedPoints = buildNormalizedPoints()

  const readTags = normalizedPoints
    .filter((point) => point.canRead && point.readTag)
    .map((point) => point.readTag)
  const writeTags = normalizedPoints
    .filter((point) => point.canWrite && point.writeTag)
    .map((point) => point.writeTag)
  const pointCatalog = normalizedPoints.map((point) => ({
    class: point.pointClass,
    canRead: point.canRead,
    readTag: point.readTag,
    canWrite: point.canWrite,
    writeTag: point.writeTag,
  }))

  if (form.value.connector_type === 'mock') {
    return {
      points: Object.fromEntries(
        normalizedPoints
          .filter((point) => point.canRead && point.readTag)
          .map((point) =>[point.readTag, parseMockValue(point.mockValue)]),
      ),
      pointCatalog,
      readTags,
      writeTags,
    }
  }

  if (form.value.connector_type === 'tdengine') {
    return {
      url: form.value.tdengineUrl.trim(),
      user: form.value.tdengineUser.trim() || 'root',
      password: form.value.tdenginePassword,
      database: form.value.tdengineDatabase.trim(),
      table_name: form.value.tdengineTableName.trim(),
      timezone: form.value.tdengineTimezone.trim() || 'Asia/Shanghai',
      pointCatalog,
      readTags,
      writeTags:[],
      return_type: 'dataframe',
    }
  }

  return {
    host: form.value.host.trim(),
    port: Number(form.value.port),
    db: Number(form.value.db),
    password: form.value.redisPassword,
    keyPrefix: form.value.keyPrefix,
    keySeparator: form.value.keySeparator || ':',
    pointCatalog,
    readTags,
    writeTags,
  }
}

function parseMockValue(value: string) {
  if (value === '') {
    return ''
  }
  const numeric = Number(value)
  return Number.isNaN(numeric) ? value : numeric
}

async function submit() {
  saving.value = true
  error.value = ''
  try {
    validateForm()
    const payload = {
      name: form.value.name.trim(),
      connector_type: form.value.connector_type,
      config: buildConfig(),
      read_enabled: form.value.read_enabled,
      write_enabled: form.value.write_enabled,
    }
    if (editingDataSourceId.value !== null) {
      await updateDataSource(editingDataSourceId.value, payload)
    } else {
      await saveDataSource(payload)
    }
    await loadDataSources()
    resetForm()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '数据源保存失败'
  } finally {
    saving.value = false
  }
}

async function remove(source: DataSourceRecord) {
  if (!window.confirm(`确认永久删除数据源「${source.name}」吗？`)) {
    return
  }
  error.value = ''
  try {
    await deleteDataSource(source.id)
    if (editingDataSourceId.value === source.id) {
      resetForm()
    }
    await loadDataSources()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '数据源删除失败'
  }
}

function pointCatalog(source: DataSourceRecord): PointCatalogView[] {
  const configured = source.config.pointCatalog ?? source.config.point_catalog
  return Array.isArray(configured) ? configured.filter(isRecord) :[]
}

function pointClass(point: PointCatalogView) {
  return point.class || point.pointClass || '未分类'
}

function readTag(point: PointCatalogView) {
  return point.readTag || point.read_tag || ''
}

function writeTag(point: PointCatalogView) {
  return point.writeTag || point.write_tag || ''
}

function canRead(point: PointCatalogView) {
  return booleanField(point.canRead, point.can_read, Boolean(readTag(point)))
}

function canWrite(point: PointCatalogView) {
  return booleanField(point.canWrite, point.can_write, Boolean(writeTag(point)))
}

function booleanField(camel: unknown, snake: unknown, fallback: boolean) {
  if (typeof camel === 'boolean') {
    return camel
  }
  if (typeof snake === 'boolean') {
    return snake
  }
  return fallback
}

function stringify(value: unknown) {
  return JSON.stringify(value, null, 2)
}

function maskSensitiveConfig(config: Record<string, unknown>) {
  const copied = { ...config }
  if (typeof copied.password === 'string' && copied.password.length > 0) {
    copied.password = '******'
  }
  return copied
}

function isRecord(value: unknown): value is PointCatalogView {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function isObjectRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function buildPointRowsFromSource(source: DataSourceRecord): PointRow[] {
  const catalog = pointCatalog(source)
  const pointValues = isObjectRecord(source.config.points) ? source.config.points : {}

  if (catalog.length > 0) {
    const mapped = catalog.map((point) => {
      const resolvedReadTag = readTag(point)
      const rawMockValue = resolvedReadTag ? pointValues[resolvedReadTag] : ''
      return {
        pointClass: pointClass(point),
        readEnabled: canRead(point),
        readTag: resolvedReadTag,
        writeEnabled: source.connector_type === 'tdengine' ? false : canWrite(point),
        writeTag: source.connector_type === 'tdengine' ? '' : writeTag(point),
        mockValue: rawMockValue === undefined || rawMockValue === null ? '' : String(rawMockValue),
      }
    })
    return mapped.length > 0 ? mapped : defaultPoints()
  }

  const readTags = Array.isArray(source.config.readTags)
    ? source.config.readTags
    : Array.isArray(source.config.read_tags)
    ? source.config.read_tags
    :[]
  const writeTags = Array.isArray(source.config.writeTags)
    ? source.config.writeTags
    : Array.isArray(source.config.write_tags)
    ? source.config.write_tags
    :[]
  const tags = Array.from(
    new Set(
      [...readTags, ...writeTags]
        .map((item) => String(item || '').trim())
        .filter(Boolean),
    ),
  )

  if (tags.length === 0) return defaultPoints()

  return tags.map((tag) => ({
    pointClass: '',
    readEnabled: readTags.includes(tag),
    readTag: readTags.includes(tag) ? tag : '',
    writeEnabled: source.connector_type === 'tdengine' ? false : writeTags.includes(tag),
    writeTag: source.connector_type === 'tdengine' ? '' : writeTags.includes(tag) ? tag : '',
    mockValue: tag in pointValues ? String(pointValues[tag]) : '',
  }))
}

function edit(source: DataSourceRecord) {
  editingDataSourceId.value = source.id
  form.value = {
    name: source.name,
    connector_type: source.connector_type,
    host: String(source.config.host ?? '127.0.0.1'),
    port: Number(source.config.port ?? 6379),
    db: Number(source.config.db ?? 0),
    redisPassword: String(source.config.password ?? ''),
    keyPrefix: String(source.config.keyPrefix ?? source.config.key_prefix ?? ''),
    keySeparator: String(source.config.keySeparator ?? source.config.key_separator ?? ':'),
    tdengineUrl: String(source.config.url ?? 'http://127.0.0.1:6041'),
    tdengineUser: String(source.config.user ?? 'root'),
    tdenginePassword: String(source.config.password ?? ''),
    tdengineDatabase: String(source.config.database ?? 'test'),
    tdengineTableName: String(source.config.table_name ?? source.config.tableName ?? 'history'),
    tdengineTimezone: String(source.config.timezone ?? 'Asia/Shanghai'),
    read_enabled: source.connector_type === 'tdengine' ? true : source.read_enabled,
    write_enabled: source.connector_type === 'tdengine' ? false : source.write_enabled,
  }
  points.value = buildPointRowsFromSource(source)
  applyConnectorTypeRules()
  error.value = ''
  showForm.value = true
}

onMounted(() => {
  applyConnectorTypeRules()
  loadDataSources()
})
</script>

<template>
  <div class="tech-container">
    <!-- Header 模块 -->
    <header class="page-header">
      <div class="header-titles">
        <span class="eyebrow">配置中心</span>
        <h1 class="page-title">数据源管控</h1>
        <p class="page-desc">配置 Mock、Redis 或 TDEngine。查询时间范围及返回内容将在实例运行时动态输入。</p>
      </div>
      <div class="header-actions" v-if="!showForm">
        <button class="tech-btn btn-ghost" @click="loadDataSources" :disabled="loading">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
          </svg>
          <span class="btn-label">{{ loading ? '刷新中...' : '刷新列表' }}</span>
        </button>
        <button class="tech-btn" @click="handleCreate">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4"/>
          </svg>
          <span class="btn-label">新增数据源</span>
        </button>
      </div>
    </header>

    <!-- 错误提示 -->
    <transition name="fade">
      <div v-if="error" class="alert-box alert-error">
        <span class="alert-icon">⚠</span> <strong>警告：</strong>{{ error }}
      </div>
    </transition>

    <transition name="fade" mode="out-in">
      <!-- 视图 1: 表单模式 (聚焦沉浸式卡片) -->
      <div v-if="showForm" class="form-wrapper">
        <div class="cyber-panel form-panel">
          <div class="corner corner-tl"></div>
          <div class="corner corner-br"></div>
          
          <div class="panel-header">
            <h2>{{ editingDataSourceId === null ? '新建数据源配置' : '编辑数据源配置' }}</h2>
            <button class="tech-btn-icon" @click="cancelEdit" title="关闭并返回">✕</button>
          </div>
          
          <form @submit.prevent="submit" class="styled-form">
            <!-- 基础配置 -->
            <fieldset class="cyber-fieldset">
              <legend>基础信息</legend>
              <div class="input-grid">
                <div class="input-item">
                  <label>数据源名称 <span class="req">*</span></label>
                  <input v-model="form.name" class="tech-input" placeholder="例如: mock-line-a" />
                </div>
                <div class="input-item">
                  <label>连接类型 <span class="req">*</span></label>
                  <select v-model="form.connector_type" class="tech-input select-arrow">
                    <option value="mock">Mock 测试数据</option>
                    <option value="redis">Redis 实时缓存</option>
                    <option value="tdengine">TDEngine 历史时序</option>
                  </select>
                </div>
              </div>
              <div class="checkbox-group">
                <label class="tech-checkbox" :class="{'is-disabled': isTdengineForm()}">
                  <input v-model="form.read_enabled" type="checkbox" :disabled="isTdengineForm()" />
                  <span class="box"></span> 允许从该源读取数据
                </label>
                <label class="tech-checkbox" :class="{'is-disabled': isTdengineForm()}">
                  <input v-model="form.write_enabled" type="checkbox" :disabled="isTdengineForm()" />
                  <span class="box"></span> {{ isTdengineForm() ? 'TDEngine 固定为只读模式' : '允许向该源回写数据' }}
                </label>
              </div>
            </fieldset>

            <!-- 连接参数 (非Mock) -->
            <fieldset class="cyber-fieldset" v-if="form.connector_type !== 'mock'">
              <legend>连接参数</legend>
              <!-- Redis Config -->
              <div v-if="form.connector_type === 'redis'" class="input-grid">
                <div class="input-item"><label>Redis Host</label><input v-model="form.host" class="tech-input" placeholder="127.0.0.1" /></div>
                <div class="input-item"><label>Redis Port</label><input v-model.number="form.port" type="number" class="tech-input" /></div>
                <div class="input-item"><label>Redis DB</label><input v-model.number="form.db" type="number" class="tech-input" /></div>
                <div class="input-item"><label>Redis 密码</label><input v-model="form.redisPassword" type="password" class="tech-input" placeholder="留空表示无密码" /></div>
                <div class="input-item"><label>Key 前缀</label><input v-model="form.keyPrefix" class="tech-input" placeholder="如 sthb" /></div>
                <div class="input-item"><label>Key 分隔符</label><input v-model="form.keySeparator" class="tech-input" placeholder="默认 :" /></div>
              </div>
              <!-- TDEngine Config -->
              <div v-if="form.connector_type === 'tdengine'" class="input-grid">
                <div class="input-item"><label>TDEngine URL</label><input v-model="form.tdengineUrl" class="tech-input" placeholder="http://127.0.0.1:6041" /></div>
                <div class="input-item"><label>用户名</label><input v-model="form.tdengineUser" class="tech-input" placeholder="root" /></div>
                <div class="input-item"><label>密码</label><input v-model="form.tdenginePassword" type="password" class="tech-input" placeholder="******" /></div>
                <div class="input-item"><label>数据库名</label><input v-model="form.tdengineDatabase" class="tech-input" placeholder="history" /></div>
                <div class="input-item"><label>表名</label><input v-model="form.tdengineTableName" class="tech-input" placeholder="point_history" /></div>
                <div class="input-item"><label>时区</label><input v-model="form.tdengineTimezone" class="tech-input" placeholder="Asia/Shanghai" /></div>
              </div>
            </fieldset>

            <!-- 位点映射 -->
            <fieldset class="cyber-fieldset">
              <div class="section-title-row">
                <legend class="legend-tight">点位映射表</legend>
                <button type="button" class="tech-btn btn-ghost btn-sm" @click="addPoint">+ 新增位点</button>
              </div>
              
              <div class="table-wrapper">
                <table class="tech-table">
                  <thead>
                    <tr>
                      <th class="col-point-type">位点类别</th>
                      <th class="col-point-read">读取配置</th>
                      <th class="col-point-write">回写配置</th>
                      <th v-if="form.connector_type === 'mock'" class="col-point-mock">Mock 默认值</th>
                      <th class="col-action">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(point, index) in points" :key="index">
                      <td>
                        <input v-model="point.pointClass" class="tech-input input-sm" placeholder="如 DCS、RTO" />
                      </td>
                      <td>
                        <div class="io-cell">
                          <label class="tech-checkbox">
                            <input v-model="point.readEnabled" type="checkbox" @change="disableRead(point)" />
                            <span class="box"></span> 读
                          </label>
                          <input v-model="point.readTag" :disabled="!point.readEnabled" class="tech-input input-sm" :placeholder="form.connector_type === 'tdengine' ? '点位编码 / 历史标签' : '读取标签'" />
                        </div>
                      </td>
                      <td>
                        <div class="io-cell" v-if="supportsWriteBindings()">
                          <label class="tech-checkbox">
                            <input v-model="point.writeEnabled" type="checkbox" @change="disableWrite(point)" />
                            <span class="box"></span> 写
                          </label>
                          <input v-model="point.writeTag" :disabled="!point.writeEnabled" class="tech-input input-sm" placeholder="回写标签" />
                        </div>
                        <div class="io-cell disabled-text" v-else>
                          <span class="tech-badge badge-ghost">禁用回写</span>
                        </div>
                      </td>
                      <td v-if="form.connector_type === 'mock'">
                        <input v-model="point.mockValue" :disabled="!point.readEnabled" class="tech-input input-sm" placeholder="如 21" />
                      </td>
                      <td class="col-action">
                        <button type="button" class="tech-btn-icon danger" @click="removePoint(index)" title="删除位点">
                           <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                        </button>
                      </td>
                    </tr>
                    <tr v-if="points.length === 0">
                      <td :colspan="form.connector_type === 'mock' ? 5 : 4" class="empty-row">
                        暂无位点映射记录，请点击上方按钮新增。
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </fieldset>

            <div class="form-actions">
              <button type="button" class="tech-btn btn-ghost" @click="cancelEdit">取消返回</button>
              <button type="submit" class="tech-btn" :disabled="saving">
                {{ saving ? '正在保存...' : (editingDataSourceId === null ? '保存数据源配置' : '保存修改') }}
              </button>
            </div>
          </form>
        </div>
      </div>

      <!-- 视图 2: 数据源列表模式 -->
      <div v-else class="list-wrapper">
        <div v-if="dataSources.length === 0 && !loading" class="empty-state cyber-panel">
          <svg width="48" height="48" fill="none" stroke="var(--cyan-main)" stroke-width="1.5" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"/>
          </svg>
          <h3>暂无数据源记录</h3>
          <p>您还没有配置任何数据源，请点击上方按钮立即创建。</p>
          <button class="tech-btn empty-action" @click="handleCreate">新建数据源</button>
        </div>

        <div class="card-grid" v-else>
          <div class="cyber-panel data-card" v-for="source in dataSources" :key="source.id">
            <div class="corner corner-tl"></div>
            <div class="corner corner-br"></div>

            <div class="card-header">
              <div class="card-title">
                <h3>{{ source.name }}</h3>
                <span class="tech-badge" :class="'badge-' + source.connector_type">{{ source.connector_type.toUpperCase() }}</span>
              </div>
            </div>
            
            <div class="card-body">
              <div class="feature-tags">
                <span class="tech-badge" :class="source.read_enabled ? 'badge-success' : 'badge-ghost'">
                  {{ source.read_enabled ? '允许读取' : '禁止读取' }}
                </span>
                <span class="tech-badge" :class="source.write_enabled ? 'badge-success' : 'badge-ghost'">
                  {{ source.write_enabled ? '允许回写' : '禁止回写' }}
                </span>
              </div>
              
              <div class="point-stats" v-if="pointCatalog(source).length > 0">
                <p class="stat-text">已映射 <span class="text-cyan">{{ pointCatalog(source).length }}</span> 个点位</p>
                <div class="point-preview">
                  <div class="point-item" v-for="(point, idx) in pointCatalog(source).slice(0, 3)" :key="idx">
                    <span class="p-class">{{ pointClass(point) }}</span>
                    <span class="p-tag">{{ readTag(point) || writeTag(point) || '未绑定' }}</span>
                  </div>
                  <div class="point-more" v-if="pointCatalog(source).length > 3">...</div>
                </div>
              </div>
              
              <!-- 折叠底层配置 -->
              <details class="config-details">
                <summary>查看底层配置 (JSON)</summary>
                <pre class="terminal-block">{{ stringify(maskSensitiveConfig(source.config)) }}</pre>
              </details>
            </div>
            
            <div class="card-footer">
              <button class="tech-btn btn-ghost btn-sm" @click="edit(source)">参数设置</button>
              <button class="tech-btn btn-danger btn-sm" @click="remove(source)">移除节点</button>
            </div>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
/* =========== 科技感主题变量 =========== */
.tech-container {
  --bg-deep: #020813;
  --panel-bg: rgba(7, 18, 36, 0.6);
  --panel-border: #14355a;
  --cyan-main: #00e5ff;
  --cyan-hover: #00b8cc;
  --cyan-glow: rgba(0, 229, 255, 0.2);
  --text-primary: #e2f1ff;
  --text-secondary: #6b8fae;
  --danger-main: #ff4d4f;
  --danger-glow: rgba(255, 77, 79, 0.2);
  --success-main: #00ff88;

  min-height: 100vh;
  background-color: var(--bg-deep);
  background-image: 
    linear-gradient(rgba(0, 229, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 229, 255, 0.03) 1px, transparent 1px);
  background-size: 20px 20px;
  background-position: center top;
  padding: 30px;
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  color: var(--text-primary);
}

.text-cyan { color: var(--cyan-main); font-weight: bold; }

/* =========== 通用动画 =========== */
.fade-enter-active, .fade-leave-active { transition: opacity 0.25s ease, transform 0.25s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; transform: translateY(10px); }

/* =========== 页面头部 =========== */
.page-header {
  display: flex; justify-content: space-between; align-items: flex-start;
  margin-bottom: 30px; padding-bottom: 15px;
  border-bottom: 1px solid var(--panel-border);
  position: relative;
}
.page-header::after {
  content: ''; position: absolute; bottom: -1px; left: 0;
  width: 80px; height: 2px; background: var(--cyan-main);
  box-shadow: 0 0 10px var(--cyan-main);
}
.eyebrow {
  display: inline-block; font-size: 12px; font-weight: bold;
  color: var(--cyan-main); margin-bottom: 8px; letter-spacing: 2px;
}
.page-title { margin: 0 0 8px; font-size: 24px; font-weight: bold; text-shadow: 0 0 10px rgba(0, 229, 255, 0.3); }
.page-desc { margin: 0; color: var(--text-secondary); font-size: 13px; }
.header-actions { display: flex; gap: 12px; margin-top: 10px; }

/* =========== 科技感按钮 =========== */
.tech-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  padding: 8px 16px; font-size: 13px; font-weight: bold;
  color: var(--cyan-main); background: rgba(0, 229, 255, 0.05);
  border: 1px solid var(--cyan-main); border-radius: 2px;
  cursor: pointer; transition: all 0.2s ease;
}
.tech-btn:hover:not(:disabled) {
  background: var(--cyan-hover); color: #000; box-shadow: 0 0 15px var(--cyan-glow);
}
.tech-btn:disabled { border-color: var(--text-secondary); color: var(--text-secondary); background: transparent; cursor: not-allowed; }

.btn-ghost { border-color: var(--panel-border); color: var(--text-primary); }
.btn-ghost:hover:not(:disabled) { border-color: var(--cyan-main); color: var(--cyan-main); background: transparent; box-shadow: inset 0 0 10px var(--cyan-glow); }

.btn-danger { border-color: var(--danger-main); color: var(--danger-main); background: rgba(255, 77, 79, 0.05); }
.btn-danger:hover:not(:disabled) { background: var(--danger-main); color: #fff; box-shadow: 0 0 15px var(--danger-glow); }

.btn-sm { padding: 6px 12px; font-size: 12px; }

.tech-btn-icon { background: none; border: none; cursor: pointer; font-size: 16px; color: var(--text-secondary); transition: 0.2s; }
.tech-btn-icon:hover { color: var(--cyan-main); text-shadow: 0 0 8px var(--cyan-glow); }
.tech-btn-icon.danger:hover { color: var(--danger-main); text-shadow: 0 0 8px var(--danger-glow); }

/* =========== HUD 面板基础样式 =========== */
.cyber-panel {
  position: relative; background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  backdrop-filter: blur(4px);
}
/* 边角装饰 */
.corner { position: absolute; width: 10px; height: 10px; }
.corner-tl { top: -1px; left: -1px; border-top: 2px solid var(--cyan-main); border-left: 2px solid var(--cyan-main); }
.corner-br { bottom: -1px; right: -1px; border-bottom: 2px solid var(--cyan-main); border-right: 2px solid var(--cyan-main); }

/* =========== 卡片列表 =========== */
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 20px; }
.data-card {
  display: flex; flex-direction: column; transition: border-color 0.3s;
}
.data-card:hover { border-color: var(--cyan-main); box-shadow: inset 0 0 15px rgba(0, 229, 255, 0.05); }

.card-header { padding: 16px 20px; border-bottom: 1px dashed var(--panel-border); }
.card-title { display: flex; justify-content: space-between; align-items: center; }
.card-title h3 { margin: 0; font-size: 16px; font-weight: bold; }

/* 标签样式 */
.tech-badge {
  padding: 2px 6px; font-size: 11px; font-family: ui-monospace, monospace;
  border: 1px solid var(--panel-border); color: var(--text-primary);
  background: rgba(0, 0, 0, 0.3); border-radius: 2px;
}
.badge-mock { border-color: var(--cyan-main); color: var(--cyan-main); background: rgba(0, 229, 255, 0.1); }
.badge-redis { border-color: var(--danger-main); color: var(--danger-main); background: rgba(255, 77, 79, 0.1); }
.badge-tdengine { border-color: var(--success-main); color: var(--success-main); background: rgba(0, 255, 136, 0.1); }
.badge-success { border-color: var(--success-main); color: var(--success-main); }
.badge-ghost { border-color: var(--text-secondary); color: var(--text-secondary); }

.card-body { padding: 20px; flex: 1; display: flex; flex-direction: column; gap: 12px; }
.feature-tags { display: flex; gap: 8px; }

.point-stats {
  background: rgba(0, 0, 0, 0.4); border: 1px solid var(--panel-border);
  padding: 12px; font-size: 12px; border-left: 2px solid var(--cyan-main);
}
.stat-text { margin: 0 0 8px; color: var(--text-secondary); }
.point-preview { display: flex; flex-direction: column; gap: 4px; }
.point-item { display: flex; justify-content: space-between; border-bottom: 1px dashed #1c3d5a; padding-bottom: 4px; }
.p-class { color: var(--text-primary); }
.p-tag { color: #a1c3e4; font-family: ui-monospace, monospace; }
.point-more { text-align: center; color: var(--text-secondary); margin-top: 2px; }

/* 终端代码块 */
.config-details { margin-top: auto; font-size: 12px; }
.config-details summary { cursor: pointer; color: var(--cyan-main); outline: none; }
.config-details summary:hover { text-shadow: 0 0 5px var(--cyan-glow); }
.terminal-block {
  background: #010408; color: var(--success-main); border: 1px solid var(--panel-border);
  padding: 10px; margin-top: 8px; overflow-x: auto; font-family: ui-monospace, monospace;
}

.card-footer {
  padding: 12px 20px; border-top: 1px solid var(--panel-border);
  display: flex; justify-content: flex-end; gap: 10px; background: rgba(0, 0, 0, 0.2);
}

/* =========== 表单与输入框 =========== */
.form-wrapper { display: flex; justify-content: center; }
.form-panel { width: 100%; max-width: 1000px; padding: 0; }
.panel-header {
  padding: 20px 24px; border-bottom: 1px solid var(--panel-border);
  display: flex; justify-content: space-between; align-items: center; background: rgba(0, 0, 0, 0.3);
}
.panel-header h2 { margin: 0; font-size: 18px; color: var(--text-primary); }

.styled-form { padding: 24px; display: flex; flex-direction: column; gap: 24px; }
.cyber-fieldset { border: 1px solid var(--panel-border); padding: 20px; background: rgba(0, 0, 0, 0.2); }
.cyber-fieldset legend { font-weight: bold; color: var(--cyan-main); padding: 0 8px; font-size: 14px; }
.legend-tight { padding: 0 8px; }

.input-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-bottom: 16px; }
.input-item label { display: block; font-size: 12px; margin-bottom: 6px; color: var(--text-secondary); }
.req { color: var(--danger-main); }

/* 暗黑输入框 */
.tech-input {
  width: 100%; padding: 8px 12px; background: #02060c; color: var(--text-primary);
  border: 1px solid var(--panel-border); font-size: 13px; font-family: ui-monospace, monospace;
  transition: all 0.2s; box-sizing: border-box; outline: none;
}
.tech-input:focus { border-color: var(--cyan-main); box-shadow: inset 0 0 8px var(--cyan-glow); }
.tech-input:disabled { background: rgba(255, 255, 255, 0.05); color: var(--text-secondary); border-color: #1a2a3a; cursor: not-allowed; }
.input-sm { padding: 6px 10px; font-size: 12px; }

/* 科技感复选框 */
.checkbox-group { display: flex; gap: 24px; padding-top: 8px; }
.tech-checkbox { display: flex; align-items: center; gap: 8px; font-size: 13px; cursor: pointer; color: var(--text-primary); }
.tech-checkbox input { appearance: none; margin: 0; width: 14px; height: 14px; border: 1px solid var(--cyan-main); background: #02060c; cursor: pointer; position: relative; }
.tech-checkbox input:checked { background: rgba(0, 229, 255, 0.2); }
.tech-checkbox input:checked::after { content: ''; position: absolute; left: 4px; top: 1px; width: 4px; height: 8px; border: solid var(--cyan-main); border-width: 0 2px 2px 0; transform: rotate(45deg); }
.tech-checkbox.is-disabled { color: var(--text-secondary); cursor: not-allowed; }
.tech-checkbox.is-disabled input { border-color: var(--panel-border); background: transparent; cursor: not-allowed; }
.tech-checkbox.is-disabled input:checked::after { border-color: var(--text-secondary); }

/* =========== 表格区域 =========== */
.section-title-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.table-wrapper { border: 1px solid var(--panel-border); background: #010308; overflow-x: auto; }
.tech-table { width: 100%; border-collapse: collapse; text-align: left; }
.tech-table th { background: rgba(20, 53, 90, 0.5); padding: 10px 12px; font-size: 12px; color: var(--text-secondary); border-bottom: 1px solid var(--cyan-main); font-weight: normal; }
.tech-table td { padding: 10px 12px; border-bottom: 1px solid #1c3d5a; vertical-align: middle; }
.tech-table tr:last-child td { border-bottom: none; }
.io-cell { display: flex; align-items: center; gap: 10px; }
.col-action { width: 50px; text-align: center; }
.col-point-type { width: 20%; }
.col-point-read, .col-point-write { width: 30%; }
.col-point-mock { width: 15%; }
.empty-row { text-align: center; padding: 24px !important; color: var(--text-secondary); font-size: 13px; font-style: italic; }

.form-actions { display: flex; justify-content: flex-end; gap: 12px; margin-top: 10px; padding-top: 20px; border-top: 1px dashed var(--panel-border); }

/* =========== 杂项提示 =========== */
.alert-error {
  background: rgba(255, 77, 79, 0.1); border: 1px solid var(--danger-main); color: var(--danger-main);
  padding: 12px 16px; margin-bottom: 24px; font-size: 13px; display: flex; align-items: center; gap: 8px;
}
.empty-state { text-align: center; padding: 60px 20px; margin-top: 20px; }
.empty-state h3 { margin: 16px 0 8px; font-size: 16px; color: var(--text-primary); }
.empty-state p { color: var(--text-secondary); margin: 0 0 20px; font-size: 13px; }

/* 滚动条适配暗黑模式 */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg-deep); }
::-webkit-scrollbar-thumb { background: #1c3d5a; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--cyan-main); }
</style>