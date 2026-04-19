<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  listPackages,
  listPackageVersions,
  runPackageVersion,
  type PluginPackageSummary,
  type RunPluginResult,
  type PluginVersionRecord,
} from '../api/packages'

const packages = ref<PluginPackageSummary[]>([])
const versions = ref<Record<string, PluginVersionRecord[]>>({})
const loading = ref(false)
const loadingVersions = ref('')
const runningVersion = ref('')
const error = ref('')
const runInputs = ref<Record<number, string>>({})
const runResults = ref<Record<number, RunPluginResult>>({})

async function loadPackages() {
  loading.value = true
  error.value = ''
  try {
    packages.value = await listPackages()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '插件包列表加载失败'
  } finally {
    loading.value = false
  }
}

async function toggleVersions(packageName: string) {
  if (versions.value[packageName]) {
    delete versions.value[packageName]
    versions.value = { ...versions.value }
    return
  }

  loadingVersions.value = packageName
  error.value = ''
  try {
    const loadedVersions = await listPackageVersions(packageName)
    versions.value = {
      ...versions.value,
      [packageName]: loadedVersions,
    }
    for (const version of loadedVersions) {
      runInputs.value[version.id] = runInputs.value[version.id] ?? '{}'
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '插件版本加载失败'
  } finally {
    loadingVersions.value = ''
  }
}

async function runVersion(packageName: string, version: PluginVersionRecord) {
  runningVersion.value = `${packageName}@${version.version}`
  error.value = ''
  try {
    const parsedInputs = JSON.parse(runInputs.value[version.id] || '{}')
    if (!parsedInputs || Array.isArray(parsedInputs) || typeof parsedInputs !== 'object') {
      throw new Error('输入 JSON 必须是对象')
    }
    const result = await runPackageVersion(packageName, version.version, parsedInputs)
    runResults.value = {
      ...runResults.value,
      [version.id]: result,
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '插件执行失败'
  } finally {
    runningVersion.value = ''
  }
}

function formatJson(value: unknown) {
  return JSON.stringify(value, null, 2)
}

onMounted(loadPackages)
</script>

<template>
  <section class="panel">
    <div class="intro page-heading">
      <div>
        <p class="eyebrow">Package Registry</p>
        <h2>插件包列表</h2>
        <p>查看已登记的插件包、最新版本和版本记录。</p>
      </div>
      <button type="button" class="secondary-button" @click="loadPackages" :disabled="loading">
        {{ loading ? '刷新中' : '刷新' }}
      </button>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="loading" class="muted">正在加载插件包。</p>

    <div v-if="!loading && packages.length === 0" class="empty-state">
      <h3>暂无插件包</h3>
      <p>上传插件包并通过 manifest 校验后，这里会出现版本记录。</p>
    </div>

    <div v-for="item in packages" :key="item.id" class="package-row">
      <div class="package-main">
        <div>
          <p class="eyebrow">{{ item.name }}</p>
          <h3>{{ item.display_name }}</h3>
          <p>{{ item.description }}</p>
        </div>
        <div class="package-meta">
          <span>{{ item.status }}</span>
          <span>{{ item.version_count }} 个版本</span>
          <span>最新 {{ item.latest_version ?? '无' }}</span>
        </div>
      </div>

      <div class="row-actions">
        <button
          type="button"
          class="secondary-button"
          @click="toggleVersions(item.name)"
          :disabled="loadingVersions === item.name"
        >
          {{ versions[item.name] ? '收起版本' : loadingVersions === item.name ? '加载中' : '查看版本' }}
        </button>
      </div>

      <div v-if="versions[item.name]" class="version-list">
        <div v-for="version in versions[item.name]" :key="version.id" class="version-row">
          <div>
            <strong>{{ version.version }}</strong>
            <span>{{ version.status }}</span>
          </div>
          <p>{{ version.digest }}</p>
          <p>{{ version.package_path }}</p>
          <label class="json-input">
            输入 JSON
            <textarea v-model="runInputs[version.id]" rows="4" spellcheck="false"></textarea>
          </label>
          <button
            type="button"
            class="secondary-button"
            @click="runVersion(item.name, version)"
            :disabled="runningVersion === `${item.name}@${version.version}`"
          >
            {{ runningVersion === `${item.name}@${version.version}` ? '执行中' : 'Dry-run 执行' }}
          </button>
          <pre v-if="runResults[version.id]">{{ formatJson(runResults[version.id]) }}</pre>
        </div>
      </div>
    </div>
  </section>
</template>
