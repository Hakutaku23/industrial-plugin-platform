<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  deleteDataSource,
  listDataSources,
  saveDataSource,
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
const error = ref('')
const form = ref({
  name: 'mock-line-a',
  connector_type: 'mock' as 'mock' | 'redis',
  host: '127.0.0.1',
  port: 6379,
  db: 0,
  keyPrefix: '',
  keySeparator: ':',
  read_enabled: true,
  write_enabled: true,
})
const points = ref<PointRow[]>([
  {
    pointClass: 'demo',
    readEnabled: true,
    readTag: 'demo:value',
    writeEnabled: true,
    writeTag: 'demo:doubled',
    mockValue: '21',
  },
])

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

function buildConfig() {
  const normalizedPoints = points.value
    .map((point) => ({
      pointClass: point.pointClass.trim(),
      canRead: point.readEnabled,
      readTag: point.readEnabled ? point.readTag.trim() : '',
      canWrite: point.writeEnabled,
      writeTag: point.writeEnabled ? point.writeTag.trim() : '',
      mockValue: point.readEnabled ? point.mockValue.trim() : '',
    }))
    .filter((point) => point.pointClass || point.readTag || point.writeTag)

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
    host: form.value.host,
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
    await saveDataSource({
      name: form.value.name,
      connector_type: form.value.connector_type,
      config: buildConfig(),
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

async function remove(source: DataSourceRecord) {
  if (!window.confirm(`删除数据源 ${source.name}？`)) {
    return
  }
  error.value = ''
  try {
    await deleteDataSource(source.id)
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

      <button type="submit" :disabled="saving">{{ saving ? '保存中' : '保存数据源' }}</button>
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
