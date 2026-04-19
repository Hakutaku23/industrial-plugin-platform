<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listRuns, type PluginRunRecord } from '../api/packages'

const runs = ref<PluginRunRecord[]>([])
const loading = ref(false)
const error = ref('')

async function loadRuns() {
  loading.value = true
  error.value = ''
  try {
    runs.value = await listRuns()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '运行记录加载失败'
  } finally {
    loading.value = false
  }
}

function stringify(value: unknown) {
  return JSON.stringify(value, null, 2)
}

onMounted(loadRuns)
</script>

<template>
  <section class="panel">
    <div class="intro page-heading">
      <div>
        <p class="eyebrow">Runs</p>
        <h2>运行记录</h2>
        <p>查看本地 dry-run 执行状态、输入与输出。</p>
      </div>
      <button type="button" class="secondary-button" @click="loadRuns" :disabled="loading">
        {{ loading ? '刷新中' : '刷新' }}
      </button>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="loading" class="muted">正在加载运行记录。</p>

    <div v-if="!loading && runs.length === 0" class="empty-state">
      <h3>暂无运行记录</h3>
      <p>在插件包列表中触发一次 dry-run 后，这里会出现记录。</p>
    </div>

    <div v-for="run in runs" :key="run.run_id" class="package-row">
      <div class="package-main">
        <div>
          <p class="eyebrow">{{ run.run_id }}</p>
          <h3>{{ run.package_name }} @ {{ run.version }}</h3>
          <p>{{ run.trigger_type }} · {{ run.environment }} · attempt {{ run.attempt }}</p>
        </div>
        <div class="package-meta">
          <span>{{ run.status }}</span>
        </div>
      </div>
      <div class="run-grid">
        <div>
          <strong>输入</strong>
          <pre>{{ stringify(run.inputs) }}</pre>
        </div>
        <div>
          <strong>输出</strong>
          <pre>{{ stringify(run.outputs) }}</pre>
        </div>
      </div>
    </div>
  </section>
</template>
