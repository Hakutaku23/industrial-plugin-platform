<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  deletePackage,
  listPackages,
  listPackageVersions,
  runPackageVersion,
  type PluginPackageSummary,
  type PluginVersionRecord,
  type RunPluginResult,
} from '../api/packages'

const packages = ref<PluginPackageSummary[]>([])
const versions = ref<Record<string, PluginVersionRecord[]>>({})
const loading = ref(false)
const loadingVersions = ref('')
const runningVersion = ref('')
const deletingPackage = ref('')
const error = ref('')
const runInputs = ref<Record<number, string>>({})
const runResults = ref<Record<number, RunPluginResult>>({})

const visibleCount = ref(10)
const currentPage = ref(1)
const PAGE_SIZE = 10

async function loadPackages() {
  loading.value = true
  error.value = ''
  try {
    packages.value = await listPackages()
    currentPage.value = 1
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

async function removePackage(item: PluginPackageSummary) {
  const confirmed = window.confirm(`确认删除插件包 ${item.name} 吗？

这会删除该插件的版本、实例、运行记录与本地存储目录。`)
  if (!confirmed) {
    return
  }

  deletingPackage.value = item.name
  error.value = ''
  try {
    await deletePackage(item.name)
    delete versions.value[item.name]
    versions.value = { ...versions.value }
    packages.value = packages.value.filter((pkg) => pkg.name !== item.name)
    if (currentPage.value > totalPages.value) {
      currentPage.value = totalPages.value
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '插件包删除失败'
  } finally {
    deletingPackage.value = ''
  }
}

const totalPages = computed(() => Math.max(1, Math.ceil(packages.value.length / PAGE_SIZE)))
const pagedPackages = computed(() => {
  const start = (currentPage.value - 1) * PAGE_SIZE
  return packages.value.slice(start, start + PAGE_SIZE)
})

function goToPage(page: number) {
  if (page < 1 || page > totalPages.value || page === currentPage.value) {
    return
  }
  currentPage.value = page
}

function formatJson(value: unknown) {
  return JSON.stringify(value, null, 2)
}

onMounted(loadPackages)
</script>

<template>
  <section class="panel plugin-list-page">
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

    <template v-else>
      <p class="muted">共 {{ packages.length }} 个插件包，每页 {{ PAGE_SIZE }} 条。</p>

      <div v-for="item in pagedPackages" :key="item.id" class="package-row">
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

        <div class="row-actions package-actions">
          <button
            type="button"
            class="secondary-button"
            @click="toggleVersions(item.name)"
            :disabled="loadingVersions === item.name || deletingPackage === item.name"
          >
            {{ versions[item.name] ? '收起版本' : loadingVersions === item.name ? '加载中' : '查看版本' }}
          </button>
          <button
            type="button"
            class="danger-button"
            @click="removePackage(item)"
            :disabled="deletingPackage === item.name || loadingVersions === item.name"
          >
            {{ deletingPackage === item.name ? '删除中' : '删除插件' }}
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

      <div class="pagination-bar" v-if="packages.length > PAGE_SIZE">
        <button type="button" class="secondary-button" @click="goToPage(currentPage - 1)" :disabled="currentPage <= 1">上一页</button>
        <span class="muted">第 {{ currentPage }} / {{ totalPages }} 页</span>
        <button type="button" class="secondary-button" @click="goToPage(currentPage + 1)" :disabled="currentPage >= totalPages">下一页</button>
      </div>
    </template>
  </section>
</template>

<style scoped>
.plugin-list-page { max-width: 920px; }
.package-actions { gap: 10px; flex-wrap: wrap; }
.pagination-bar { display: flex; align-items: center; justify-content: flex-end; gap: 10px; margin-top: 18px; }
</style>
