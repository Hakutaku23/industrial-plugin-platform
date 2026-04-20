<script setup lang="ts">
import { onMounted, ref } from 'vue'
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

function defaultForm() {
  return {
    name: 'mock-line-a',
    connector_type: 'mock' as 'mock' | 'redis',
    host: '127.0.0.1',
    port: 6379,
    db: 0,
    keyPrefix: '',
    keySeparator: ':',
    read_enabled: true,
    write_enabled: true,
  }
}

function defaultPoints(): PointRow[] {
  return [
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
}

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
      canWrite: point.writeEnabled,
      writeTag: point.writeEnabled ? point.writeTag.trim() : '',
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
          .map((point) => [point.readTag, parseMockValue(point.mockValue)]),
      ),
      pointCatalog,
      readTags,
      writeTags,
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
  if (!window.confirm(`删除数据源 ${source.name}？`)) {
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
  return Array.isArray(configured) ? configured.filter(isRecord) : []
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
        writeEnabled: canWrite(point),
        writeTag: writeTag(point),
        mockValue: rawMockValue === undefined || rawMockValue === null ? '' : String(rawMockValue),
      }
    })
    return mapped.length > 0 ? mapped : defaultPoints()
  }

  const readTags = Array.isArray(source.config.readTags)
    ? source.config.readTags
    : Array.isArray(source.config.read_tags)
      ? source.config.read_tags
      : []
  const writeTags = Array.isArray(source.config.writeTags)
    ? source.config.writeTags
    : Array.isArray(source.config.write_tags)
      ? source.config.write_tags
      : []
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
    writeEnabled: writeTags.includes(tag),
    writeTag: writeTags.includes(tag) ? tag : '',
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
    read_enabled: source.read_enabled,
    write_enabled: source.write_enabled,
  }
  points.value = buildPointRowsFromSource(source)
  error.value = ''
}

onMounted(loadDataSources)
</script>

<template>
  <section class="panel">
    <div class="intro page-heading">
      <div>
        <p class="eyebrow">Connectors</p>
        <h2>数据源与位点</h2>
        <p>配置 Mock 或 Redis 数据源，并为每个点独立声明读取和回写权限。</p>
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
        <select v-model="form.connector_type">
          <option value="mock">Mock</option>
          <option value="redis">Redis</option>
        </select>
      </label>
      <label class="checkbox-line">
        <input v-model="form.read_enabled" type="checkbox" />
        数据源允许读取
      </label>
      <label class="checkbox-line">
        <input v-model="form.write_enabled" type="checkbox" />
        数据源允许回写
      </label>

      <template v-if="form.connector_type === 'redis'">
        <label>
          Redis Host
          <input v-model="form.host" />
        </label>
        <label>
          Redis Port
          <input v-model.number="form.port" type="number" />
        </label>
        <label>
          Redis DB
          <input v-model.number="form.db" type="number" />
        </label>
        <label>
          Key 前缀
          <input v-model="form.keyPrefix" placeholder="如 sthb" />
        </label>
        <label>
          Key 分隔符
          <input v-model="form.keySeparator" placeholder="默认 :" />
        </label>
      </template>

      <div class="wide-field">
        <div class="section-title">
          <strong>位点</strong>
          <button type="button" class="secondary-button" @click="addPoint">新增位点</button>
        </div>
        <div class="point-grid point-grid-head" :class="{ 'point-grid-mock': form.connector_type === 'mock' }">
          <span>点所属类</span>
          <span>读取</span>
          <span>读取标签 / Redis 位点名</span>
          <span>回写</span>
          <span>回写标签 / Redis 位点名</span>
          <span v-if="form.connector_type === 'mock'">Mock 值</span>
          <span>操作</span>
        </div>
        <div
          v-for="(point, index) in points"
          :key="index"
          class="point-grid"
          :class="{ 'point-grid-mock': form.connector_type === 'mock' }"
        >
          <input v-model="point.pointClass" placeholder="如 DCS、RTO、pressure" />
          <label class="inline-check">
            <input v-model="point.readEnabled" type="checkbox" @change="disableRead(point)" />
            可读
          </label>
          <input
            v-model="point.readTag"
            :disabled="!point.readEnabled"
            placeholder="如 DCS_AO_RTO_014_AI"
          />
          <label class="inline-check">
            <input v-model="point.writeEnabled" type="checkbox" @change="disableWrite(point)" />
            可写
          </label>
          <input
            v-model="point.writeTag"
            :disabled="!point.writeEnabled"
            placeholder="如 DCS_AO_RTO_020_AI"
          />
          <input
            v-if="form.connector_type === 'mock'"
            v-model="point.mockValue"
            :disabled="!point.readEnabled"
            placeholder="如 21"
          />
          <button type="button" class="danger-button" @click="removePoint(index)">删除</button>
        </div>
      </div>

      <div class="row-actions wide-field">
        <button type="submit" :disabled="saving">
          {{ saving ? '保存中' : editingDataSourceId === null ? '保存数据源' : '保存修改' }}
        </button>
        <button v-if="editingDataSourceId !== null" type="button" class="secondary-button" @click="resetForm">
          取消编辑
        </button>
      </div>
    </form>

    <div v-for="source in dataSources" :key="source.id" class="package-row">
      <div class="package-main">
        <div>
          <p class="eyebrow">{{ source.connector_type }}</p>
          <h3>{{ source.name }}</h3>
          <p>{{ source.read_enabled ? '数据源可读取' : '数据源不可读取' }} · {{ source.write_enabled ? '数据源可回写' : '数据源不可回写' }}</p>
        </div>
        <div class="package-meta">
          <span>{{ source.status }}</span>
        </div>
      </div>
      <div class="row-actions">
        <button type="button" class="secondary-button" @click="edit(source)">修改</button>
        <button type="button" class="danger-button" @click="remove(source)">删除</button>
      </div>
      <div v-if="pointCatalog(source).length > 0" class="point-list">
        <div v-for="(point, index) in pointCatalog(source)" :key="index" class="point-summary">
          <strong>{{ pointClass(point) }}</strong>
          <span>{{ canRead(point) ? `读：${readTag(point) || '未填'}` : '不可读' }}</span>
          <span>{{ canWrite(point) ? `写：${writeTag(point) || '未填'}` : '不可写' }}</span>
        </div>
      </div>
      <pre>{{ stringify(source.config) }}</pre>
    </div>
  </section>
</template>
