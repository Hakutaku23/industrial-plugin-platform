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
  <div class="humanized-container">
    <!-- Header 模块 -->
    <header class="page-header">
      <div class="header-titles">
        <span class="tag-eyebrow">Connectors</span>
        <h1 class="page-title">数据源与位点</h1>
        <p class="page-desc">配置 Mock、Redis 或 TDEngine。查询时间范围及返回内容将在实例运行时动态输入。</p>
      </div>
      <div class="header-actions" v-if="!showForm">
        <button class="btn btn-secondary" @click="loadDataSources" :disabled="loading">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
          <span style="margin-left: 6px">{{ loading ? '刷新中...' : '刷新列表' }}</span>
        </button>
        <button class="btn btn-primary" @click="handleCreate">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4"/></svg>
          <span style="margin-left: 6px">新增数据源</span>
        </button>
      </div>
    </header>

    <!-- 错误提示 -->
    <transition name="fade">
      <div v-if="error" class="alert-box">
        <strong>出错了：</strong>{{ error }}
      </div>
    </transition>

    <transition name="fade" mode="out-in">
      <!-- 视图 1: 表单模式 (聚焦沉浸式卡片) -->
      <div v-if="showForm" class="form-wrapper">
        <div class="form-card">
          <div class="form-header">
            <h2>{{ editingDataSourceId === null ? '新建数据源配置' : '编辑数据源配置' }}</h2>
            <button class="btn-icon" @click="cancelEdit" title="关闭并返回">✕</button>
          </div>
          
          <form @submit.prevent="submit" class="styled-form">
            <!-- 基础配置 -->
            <fieldset class="form-section">
              <legend>基础信息</legend>
              <div class="input-grid">
                <div class="input-item">
                  <label>数据源名称 <span class="req">*</span></label>
                  <input v-model="form.name" class="v-input" placeholder="例如: mock-line-a" />
                </div>
                <div class="input-item">
                  <label>连接类型 <span class="req">*</span></label>
                  <select v-model="form.connector_type" class="v-input">
                    <option value="mock">Mock 测试数据</option>
                    <option value="redis">Redis 实时缓存</option>
                    <option value="tdengine">TDEngine 历史时序</option>
                  </select>
                </div>
              </div>
              <div class="checkbox-group">
                <label class="custom-checkbox" :class="{'is-disabled': isTdengineForm()}">
                  <input v-model="form.read_enabled" type="checkbox" :disabled="isTdengineForm()" />
                  <span class="box"></span> 允许从该源读取数据
                </label>
                <label class="custom-checkbox" :class="{'is-disabled': isTdengineForm()}">
                  <input v-model="form.write_enabled" type="checkbox" :disabled="isTdengineForm()" />
                  <span class="box"></span> {{ isTdengineForm() ? 'TDEngine 固定为只读模式' : '允许向该源回写数据' }}
                </label>
              </div>
            </fieldset>

            <!-- 连接参数 (非Mock) -->
            <fieldset class="form-section bg-light" v-if="form.connector_type !== 'mock'">
              <legend>连接参数</legend>
              <!-- Redis Config -->
              <div v-if="form.connector_type === 'redis'" class="input-grid">
                <div class="input-item"><label>Redis Host</label><input v-model="form.host" class="v-input" placeholder="127.0.0.1" /></div>
                <div class="input-item"><label>Redis Port</label><input v-model.number="form.port" type="number" class="v-input" /></div>
                <div class="input-item"><label>Redis DB</label><input v-model.number="form.db" type="number" class="v-input" /></div>
                <div class="input-item"><label>Key 前缀</label><input v-model="form.keyPrefix" class="v-input" placeholder="如 sthb" /></div>
                <div class="input-item"><label>Key 分隔符</label><input v-model="form.keySeparator" class="v-input" placeholder="默认 :" /></div>
              </div>
              <!-- TDEngine Config -->
              <div v-if="form.connector_type === 'tdengine'" class="input-grid">
                <div class="input-item"><label>TDEngine URL</label><input v-model="form.tdengineUrl" class="v-input" placeholder="http://127.0.0.1:6041" /></div>
                <div class="input-item"><label>用户名</label><input v-model="form.tdengineUser" class="v-input" placeholder="root" /></div>
                <div class="input-item"><label>密码</label><input v-model="form.tdenginePassword" type="password" class="v-input" placeholder="******" /></div>
                <div class="input-item"><label>数据库名</label><input v-model="form.tdengineDatabase" class="v-input" placeholder="history" /></div>
                <div class="input-item"><label>表名</label><input v-model="form.tdengineTableName" class="v-input" placeholder="point_history" /></div>
                <div class="input-item"><label>时区</label><input v-model="form.tdengineTimezone" class="v-input" placeholder="Asia/Shanghai" /></div>
              </div>
            </fieldset>

            <!-- 位点映射 -->
            <fieldset class="form-section">
              <div class="section-title-row">
                <legend style="padding:0">点位映射表</legend>
                <button type="button" class="btn btn-sm btn-outline" @click="addPoint">+ 新增位点</button>
              </div>
              
              <div class="table-wrapper">
                <table class="point-table">
                  <thead>
                    <tr>
                      <th style="width: 20%">位点类别</th>
                      <th style="width: 30%">读取配置</th>
                      <th style="width: 30%">回写配置</th>
                      <th v-if="form.connector_type === 'mock'" style="width: 15%">Mock 默认值</th>
                      <th class="col-action">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(point, index) in points" :key="index">
                      <td>
                        <input v-model="point.pointClass" class="v-input v-sm" placeholder="如 DCS、RTO" />
                      </td>
                      <td>
                        <div class="io-cell">
                          <label class="custom-checkbox">
                            <input v-model="point.readEnabled" type="checkbox" @change="disableRead(point)" />
                            <span class="box"></span> 读
                          </label>
                          <input v-model="point.readTag" :disabled="!point.readEnabled" class="v-input v-sm" :placeholder="form.connector_type === 'tdengine' ? '点位编码 / 历史标签' : '读取标签'" />
                        </div>
                      </td>
                      <td>
                        <div class="io-cell" v-if="supportsWriteBindings()">
                          <label class="custom-checkbox">
                            <input v-model="point.writeEnabled" type="checkbox" @change="disableWrite(point)" />
                            <span class="box"></span> 写
                          </label>
                          <input v-model="point.writeTag" :disabled="!point.writeEnabled" class="v-input v-sm" placeholder="回写标签" />
                        </div>
                        <div class="io-cell disabled-text" v-else>
                          <span class="tag tag-disabled">TDEngine 禁用回写</span>
                        </div>
                      </td>
                      <td v-if="form.connector_type === 'mock'">
                        <input v-model="point.mockValue" :disabled="!point.readEnabled" class="v-input v-sm" placeholder="如 21" />
                      </td>
                      <td class="col-action">
                        <button type="button" class="btn-icon danger" @click="removePoint(index)" title="删除位点">
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
              <button type="button" class="btn btn-secondary" @click="cancelEdit">取消返回</button>
              <button type="submit" class="btn btn-primary" :disabled="saving">
                {{ saving ? '正在保存...' : (editingDataSourceId === null ? '保存数据源' : '保存修改') }}
              </button>
            </div>
          </form>
        </div>
      </div>

      <!-- 视图 2: 数据源列表模式 -->
      <div v-else class="list-wrapper">
        <div v-if="dataSources.length === 0 && !loading" class="empty-state">
          <svg width="64" height="64" fill="none" stroke="#cbd5e1" stroke-width="1.5" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"/>
          </svg>
          <h3>暂无数据源记录</h3>
          <p>您还没有配置任何数据源，请点击上方按钮立即创建。</p>
          <button class="btn btn-primary" @click="handleCreate" style="margin-top: 12px">新建数据源</button>
        </div>

        <div class="card-grid" v-else>
          <div class="data-card" v-for="source in dataSources" :key="source.id">
            <div class="card-header">
              <div class="card-title">
                <h3>{{ source.name }}</h3>
                <span class="badge" :class="'badge-' + source.connector_type">{{ source.connector_type.toUpperCase() }}</span>
              </div>
              <span class="status-indicator" :class="source.status === 'active' ? 'active' : ''"></span>
            </div>
            
            <div class="card-body">
              <div class="feature-tags">
                <span class="tag" :class="source.read_enabled ? 'tag-success' : 'tag-disabled'">
                  {{ source.read_enabled ? '✓ 支持读取' : '✗ 禁止读取' }}
                </span>
                <span class="tag" :class="source.write_enabled ? 'tag-success' : 'tag-disabled'">
                  {{ source.write_enabled ? '✓ 支持回写' : '✗ 禁止回写' }}
                </span>
              </div>
              
              <div class="point-stats" v-if="pointCatalog(source).length > 0">
                <p class="stat-text">已映射 <strong>{{ pointCatalog(source).length }}</strong> 个点位</p>
                <div class="point-preview">
                  <div class="point-item" v-for="(point, idx) in pointCatalog(source).slice(0, 3)" :key="idx">
                    <span class="p-class">{{ pointClass(point) }}</span>
                    <span class="p-tag">{{ readTag(point) || writeTag(point) || '未绑定' }}</span>
                  </div>
                  <div class="point-more" v-if="pointCatalog(source).length > 3">...等</div>
                </div>
              </div>
              
              <!-- 折叠底层配置 -->
              <details class="config-details">
                <summary>查看底层配置 (JSON)</summary>
                <pre class="code-block">{{ stringify(source.config) }}</pre>
              </details>
            </div>
            
            <div class="card-footer">
              <button class="btn btn-ghost" @click="edit(source)">参数设置</button>
              <button class="btn btn-ghost danger" @click="remove(source)">移除该源</button>
            </div>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
/* =========== 设计系统变量 =========== */
.humanized-container {
  --c-primary: #3b82f6;
  --c-primary-hover: #2563eb;
  --c-danger: #ef4444;
  --c-danger-hover: #dc2626;
  --c-text: #1e293b;
  --c-text-light: #64748b;
  --c-border: #e2e8f0;
  --c-bg: #f8fafc;
  --c-card: #ffffff;
  --radius: 12px;
  --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
  --shadow-hover: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
  
  max-width: 1320px;
  margin: 0 auto;
  padding: 24px;
  color: var(--c-text);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}

/* =========== 通用动画 =========== */
.fade-enter-active, .fade-leave-active { transition: opacity 0.25s ease, transform 0.25s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; transform: translateY(8px); }

/* =========== 页面头部 =========== */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 32px;
}
.tag-eyebrow {
  display: inline-block;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--c-primary);
  margin-bottom: 8px;
}
.page-title { margin: 0 0 8px; font-size: 28px; font-weight: 700; color: #0f172a;}
.page-desc { margin: 0; color: var(--c-text-light); font-size: 14px; }
.header-actions { display: flex; gap: 12px; }

/* =========== 按钮基类 =========== */
.btn {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 8px 16px; border-radius: 6px; font-size: 14px; font-weight: 500;
  cursor: pointer; border: 1px solid transparent; transition: all 0.2s;
}
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-primary { background: var(--c-primary); color: white; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
.btn-primary:hover:not(:disabled) { background: var(--c-primary-hover); }
.btn-secondary { background: white; border-color: var(--c-border); color: var(--c-text); }
.btn-secondary:hover:not(:disabled) { background: var(--c-bg); border-color: #cbd5e1; }
.btn-outline { background: transparent; border-color: var(--c-primary); color: var(--c-primary); }
.btn-outline:hover { background: #eff6ff; }
.btn-ghost { background: transparent; color: var(--c-text-light); }
.btn-ghost:hover { background: var(--c-bg); color: var(--c-text); }
.btn-ghost.danger:hover { color: var(--c-danger); background: #fef2f2; }
.btn-sm { padding: 6px 12px; font-size: 13px; }
.btn-icon { background: none; border: none; cursor: pointer; font-size: 20px; color: var(--c-text-light); transition: 0.2s;}
.btn-icon:hover { color: var(--c-text); }
.btn-icon.danger:hover { color: var(--c-danger); }

/* =========== 卡片列表 =========== */
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 24px;
}
.data-card {
  background: var(--c-card); border: 1px solid var(--c-border);
  border-radius: var(--radius); box-shadow: var(--shadow);
  display: flex; flex-direction: column; transition: all 0.2s ease;
}
.data-card:hover { transform: translateY(-4px); box-shadow: var(--shadow-hover); border-color: #cbd5e1; }
.card-header {
  padding: 20px 20px 16px; border-bottom: 1px solid var(--c-border);
  display: flex; justify-content: space-between; align-items: flex-start;
}
.card-title h3 { margin: 0 0 8px; font-size: 18px; color: #0f172a; }
.badge { font-size: 12px; padding: 4px 8px; border-radius: 4px; font-weight: 600; }
.badge-mock { background: #f1f5f9; color: #475569; }
.badge-redis { background: #fee2e2; color: #991b1b; }
.badge-tdengine { background: #e0f2fe; color: #075985; }
.card-body { padding: 20px; flex: 1; }
.feature-tags { display: flex; gap: 8px; margin-bottom: 16px; }
.tag { font-size: 12px; padding: 4px 8px; border-radius: 4px; font-weight: 500;}
.tag-success { background: #dcfce7; color: #166534; }
.tag-disabled { background: #f1f5f9; color: #94a3b8; }
.point-stats { background: #f8fafc; border-radius: 8px; padding: 12px; margin-bottom: 16px; border: 1px dashed var(--c-border); }
.stat-text { margin: 0 0 8px; font-size: 13px; color: var(--c-text-light); }
.point-preview { display: flex; flex-direction: column; gap: 6px; }
.point-item { display: flex; justify-content: space-between; font-size: 12px; border-bottom: 1px dotted #cbd5e1; padding-bottom: 4px; }
.p-class { font-weight: 600; color: #334155; }
.p-tag { color: var(--c-text-light); font-family: monospace;}
.point-more { font-size: 12px; color: var(--c-text-light); text-align: center; margin-top: 4px; }
.config-details { font-size: 13px; margin-top: auto;}
.config-details summary { cursor: pointer; color: var(--c-text-light); outline: none; transition: color 0.2s;}
.config-details summary:hover { color: var(--c-primary); }
.code-block { background: #1e293b; color: #f8fafc; padding: 12px; border-radius: 6px; overflow-x: auto; font-size: 12px; margin-top: 8px; font-family: monospace;}
.card-footer { padding: 12px 20px; border-top: 1px solid var(--c-border); display: flex; justify-content: flex-end; gap: 8px; background: #f8fafc; border-radius: 0 0 var(--radius) var(--radius); }

/* =========== 表单与输入框 =========== */
.form-wrapper { display: flex; justify-content: center; animation: fade-in 0.3s ease; }
.form-card { background: var(--c-card); border-radius: var(--radius); box-shadow: var(--shadow-hover); width: 100%; max-width: 1000px; border: 1px solid var(--c-border); }
.form-header { padding: 24px; border-bottom: 1px solid var(--c-border); display: flex; justify-content: space-between; align-items: center; background: #f8fafc; border-radius: var(--radius) var(--radius) 0 0; }
.form-header h2 { margin: 0; font-size: 20px; color: #0f172a;}
.styled-form { padding: 32px 24px; }
.form-section { border: 1px solid var(--c-border); border-radius: 8px; padding: 24px; margin-bottom: 24px; }
.form-section legend { font-weight: 600; padding: 0 8px; color: var(--c-primary); font-size: 15px; }
.bg-light { background: #f8fafc; }
.input-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 20px; margin-bottom: 20px; }
.input-item label { display: block; font-size: 13px; font-weight: 500; margin-bottom: 8px; color: #334155;}
.req { color: var(--c-danger); }
.v-input { width: 100%; padding: 10px 12px; border: 1px solid var(--c-border); border-radius: 6px; font-size: 14px; transition: border-color 0.2s, box-shadow 0.2s; box-sizing: border-box; }
.v-input:focus { border-color: var(--c-primary); outline: none; box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1); }
.v-input:disabled { background: #f1f5f9; color: #94a3b8; cursor: not-allowed; }
.custom-checkbox { display: flex; align-items: center; gap: 8px; font-size: 14px; cursor: pointer; color: #334155; }
.custom-checkbox.is-disabled { opacity: 0.6; cursor: not-allowed; }
.custom-checkbox input { accent-color: var(--c-primary); width: 16px; height: 16px; cursor: pointer;}
.checkbox-group { display: flex; gap: 32px; padding-top: 8px; }

/* =========== 表格 (替代原有的粗糙Grid) =========== */
.section-title-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.table-wrapper { overflow-x: auto; border: 1px solid var(--c-border); border-radius: 8px; }
.point-table { width: 100%; border-collapse: collapse; text-align: left; }
.point-table th { background: #f8fafc; padding: 12px 16px; font-size: 13px; font-weight: 600; color: #475569; border-bottom: 1px solid var(--c-border); }
.point-table td { padding: 12px 16px; border-bottom: 1px solid var(--c-border); vertical-align: top; }
.point-table tr:last-child td { border-bottom: none; }
.io-cell { display: flex; align-items: center; gap: 12px; }
.v-sm { padding: 8px 10px; font-size: 13px; flex: 1; }
.col-action { width: 60px; text-align: center; }
.empty-row { text-align: center; padding: 32px !important; color: var(--c-text-light); font-size: 14px; background: #fafafa; }
.form-actions { display: flex; justify-content: flex-end; gap: 16px; margin-top: 32px; padding-top: 24px; border-top: 1px solid var(--c-border); }

/* =========== 杂项提示 =========== */
.alert-box { background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; padding: 12px 16px; border-radius: 8px; margin-bottom: 24px; font-size: 14px; display: flex; align-items: center; }
.empty-state { text-align: center; padding: 80px 20px; background: white; border-radius: 12px; border: 1px dashed var(--c-border); }
.empty-state h3 { margin: 16px 0 8px; font-size: 18px; color: #334155;}
.empty-state p { color: var(--c-text-light); margin: 0 0 24px; font-size: 14px; }
</style>