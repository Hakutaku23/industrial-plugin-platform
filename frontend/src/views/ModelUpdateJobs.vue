<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  listDataSources,
  listPackages,
  listPackageVersions,
  type DataSourceRecord,
  type PluginPackageSummary,
  type PluginVersionRecord,
} from '../api/packages'
import { listModels, type ModelSummary } from '../api/models'
import {
  createModelUpdateJob,
  deleteModelUpdateJob,
  getModelUpdateSchedulerStatus,
  listModelUpdateCandidates,
  listModelUpdateJobs,
  listModelUpdateRuns,
  promoteModelUpdateCandidate,
  rejectModelUpdateCandidate,
  runDueModelUpdateJobs,
  runModelUpdateJob,
  updateModelUpdateJob,
  type HistoryWindowConfig,
  type ModelUpdateCandidate,
  type ModelUpdateInputBinding,
  type ModelUpdateJob,
  type ModelUpdateRun,
  type ModelUpdateSchedulerStatus,
} from '../api/modelUpdates'

type BindingType = 'single' | 'batch' | 'history'

const jobs = ref<ModelUpdateJob[]>([])
const models = ref<ModelSummary[]>([])
const packages = ref<PluginPackageSummary[]>([])
const versions = ref<PluginVersionRecord[]>([])
const dataSources = ref<DataSourceRecord[]>([])
const runs = ref<ModelUpdateRun[]>([])
const candidates = ref<ModelUpdateCandidate[]>([])
const selectedJobId = ref<number | null>(null)
const loading = ref(false)
const operating = ref(false)
const error = ref('')
const notice = ref('')
const schedulerStatus = ref<ModelUpdateSchedulerStatus | null>(null)

const form = ref({
  id: null as number | null,
  name: 'redis-sine-model-update',
  model_id: '',
  trainer_package_name: '',
  trainer_package_version: '',
  schedule_enabled: false,
  schedule_interval_sec: 86400,
  promote_mode: 'manual',
  configText: '{}',
})

const inputBindings = ref<ModelUpdateInputBinding[]>([])

const selectedJob = computed(() => jobs.value.find((item) => item.id === selectedJobId.value) ?? null)
const selectedModel = computed(() => models.value.find((item) => item.id === Number(form.value.model_id)) ?? null)
const trainerVersions = computed(() => versions.value)

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const [jobItems, modelItems, packageItems, dataSourceItems, scheduler] = await Promise.all([
      listModelUpdateJobs(),
      listModels(),
      listPackages(),
      listDataSources(),
      getModelUpdateSchedulerStatus().catch(() => null),
    ])
    jobs.value = jobItems
    models.value = modelItems
    packages.value = packageItems
    dataSources.value = dataSourceItems
    schedulerStatus.value = scheduler
    if (!selectedJobId.value && jobs.value.length > 0) {
      await selectJob(jobs.value[0])
    }
    if (!form.value.model_id && models.value.length > 0) {
      form.value.model_id = String(models.value[0].id)
    }
    if (!form.value.trainer_package_name) {
      const trainer = packages.value.find((item) => String(item.name).includes('trainer')) ?? packages.value[0]
      if (trainer) {
        form.value.trainer_package_name = trainer.name
        await onTrainerPackageChange()
      }
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '模型更新任务加载失败'
  } finally {
    loading.value = false
  }
}

async function refreshScheduler() {
  schedulerStatus.value = await getModelUpdateSchedulerStatus()
}

async function scanDueJobs() {
  operating.value = true
  error.value = ''
  notice.value = ''
  try {
    const result = await runDueModelUpdateJobs()
    notice.value = `到期任务扫描完成：${JSON.stringify(result)}`
    await loadAll()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '扫描到期任务失败'
  } finally {
    operating.value = false
  }
}

async function onTrainerPackageChange() {
  versions.value = form.value.trainer_package_name ? await listPackageVersions(form.value.trainer_package_name) : []
  form.value.trainer_package_version = versions.value[0]?.version ?? ''
  ensureDefaultHistoryBinding()
}

async function selectJob(job: ModelUpdateJob) {
  selectedJobId.value = job.id
  form.value = {
    id: job.id,
    name: job.name,
    model_id: String(job.model_id),
    trainer_package_name: job.trainer_package_name,
    trainer_package_version: job.trainer_package_version,
    schedule_enabled: job.schedule_enabled,
    schedule_interval_sec: job.schedule_interval_sec,
    promote_mode: job.promote_mode || 'manual',
    configText: JSON.stringify(job.config || {}, null, 2),
  }
  inputBindings.value = (job.input_bindings || []).map((item) => ({ ...item }))
  await onTrainerPackageChange()
  form.value.trainer_package_version = job.trainer_package_version
  await loadJobDetails(job.id)
}

async function loadJobDetails(jobId: number) {
  const [runItems, candidateItems] = await Promise.all([
    listModelUpdateRuns(jobId),
    listModelUpdateCandidates(jobId),
  ])
  runs.value = runItems
  candidates.value = candidateItems
}

function resetForm() {
  form.value = {
    id: null,
    name: 'redis-sine-model-update',
    model_id: models.value[0] ? String(models.value[0].id) : '',
    trainer_package_name: '',
    trainer_package_version: '',
    schedule_enabled: false,
    schedule_interval_sec: 86400,
    promote_mode: 'manual',
    configText: '{}',
  }
  inputBindings.value = []
  selectedJobId.value = null
  runs.value = []
  candidates.value = []
}

function defaultHistoryWindow(): HistoryWindowConfig {
  return {
    start_offset_min: 10080,
    end_offset_min: 0,
    sample_interval_sec: 60,
    lookback_before_start_sec: 600,
    fill_method: 'ffill_then_interpolate',
    strict_first_value: true,
  }
}

function defaultBinding(type: BindingType = 'history'): ModelUpdateInputBinding {
  const source = dataSources.value.find((item) => item.connector_type === 'tdengine') ?? dataSources.value[0]
  if (type === 'single') {
    return { binding_type: 'single', input_name: 'input_014', data_source_id: source?.id ?? 0, source_tag: '' }
  }
  if (type === 'batch') {
    return { binding_type: 'batch', input_name: '', data_source_id: source?.id ?? 0, source_mappings: [], output_format: 'named-map' }
  }
  return {
    binding_type: 'history',
    input_name: 'training_window',
    data_source_id: source?.id ?? 0,
    source_tags: [],
    window: defaultHistoryWindow(),
  }
}

function ensureDefaultHistoryBinding() {
  if (inputBindings.value.length === 0) {
    inputBindings.value.push(defaultBinding('history'))
  }
}

function addBinding(type: BindingType = 'history') {
  inputBindings.value.push(defaultBinding(type))
}

function removeBinding(index: number) {
  inputBindings.value.splice(index, 1)
}

function addMapping(binding: ModelUpdateInputBinding) {
  const mappings = binding.source_mappings || []
  mappings.push({ tag: '', key: '' })
  binding.source_mappings = mappings
}

function removeMapping(binding: ModelUpdateInputBinding, index: number) {
  binding.source_mappings = (binding.source_mappings || []).filter((_, current) => current !== index)
}

function addSourceTag(binding: ModelUpdateInputBinding) {
  const tags = binding.source_tags || []
  tags.push('')
  binding.source_tags = tags
}

function removeSourceTag(binding: ModelUpdateInputBinding, index: number) {
  binding.source_tags = (binding.source_tags || []).filter((_, current) => current !== index)
}

function normalizePayload() {
  if (!form.value.name.trim()) throw new Error('请填写任务名称')
  if (!form.value.model_id) throw new Error('请选择目标模型')
  if (!form.value.trainer_package_name || !form.value.trainer_package_version) throw new Error('请选择训练插件包和版本')
  let config: Record<string, unknown> = {}
  try {
    config = JSON.parse(form.value.configText || '{}')
  } catch {
    throw new Error('训练配置 JSON 不合法')
  }
  return {
    name: form.value.name.trim(),
    model_id: Number(form.value.model_id),
    trainer_package_name: form.value.trainer_package_name,
    trainer_package_version: form.value.trainer_package_version,
    input_bindings: inputBindings.value
      .filter((item) => item.data_source_id)
      .map((item) => ({ ...item, data_source_id: Number(item.data_source_id) })),
    schedule_enabled: form.value.schedule_enabled,
    schedule_interval_sec: Math.max(60, Number(form.value.schedule_interval_sec || 86400)),
    promote_mode: form.value.promote_mode,
    config,
  }
}

async function saveJob() {
  operating.value = true
  error.value = ''
  notice.value = ''
  try {
    const payload = normalizePayload()
    const saved = form.value.id
      ? await updateModelUpdateJob(form.value.id, payload)
      : await createModelUpdateJob(payload)
    notice.value = form.value.id ? '模型更新任务已保存' : '模型更新任务已创建'
    await loadAll()
    await selectJob(saved)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '保存模型更新任务失败'
  } finally {
    operating.value = false
  }
}

async function deleteSelectedJob() {
  if (!form.value.id) return
  operating.value = true
  error.value = ''
  notice.value = ''
  try {
    await deleteModelUpdateJob(form.value.id)
    notice.value = '模型更新任务已删除'
    resetForm()
    await loadAll()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '删除模型更新任务失败'
  } finally {
    operating.value = false
  }
}

async function runSelectedJob() {
  if (!form.value.id) return
  operating.value = true
  error.value = ''
  notice.value = ''
  try {
    await runModelUpdateJob(form.value.id)
    notice.value = '模型更新任务执行完成'
    await loadAll()
    if (form.value.id) await loadJobDetails(form.value.id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '执行模型更新任务失败'
  } finally {
    operating.value = false
  }
}

async function promoteCandidate(candidate: ModelUpdateCandidate) {
  operating.value = true
  error.value = ''
  notice.value = ''
  try {
    await promoteModelUpdateCandidate(candidate.id)
    notice.value = '候选模型已上线'
    if (form.value.id) await loadJobDetails(form.value.id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '候选模型上线失败'
  } finally {
    operating.value = false
  }
}

async function rejectCandidate(candidate: ModelUpdateCandidate) {
  operating.value = true
  error.value = ''
  notice.value = ''
  try {
    await rejectModelUpdateCandidate(candidate.id)
    notice.value = '候选模型已驳回'
    if (form.value.id) await loadJobDetails(form.value.id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '候选模型驳回失败'
  } finally {
    operating.value = false
  }
}

function dataSourceName(id: number | undefined) {
  return dataSources.value.find((item) => item.id === Number(id))?.name || '-'
}

function metricValue(candidate: ModelUpdateCandidate, key: string) {
  const metrics = candidate.metrics?.metrics
  if (metrics && typeof metrics === 'object' && key in metrics) {
    return String((metrics as Record<string, unknown>)[key])
  }
  return 'N/A'
}

watch(() => form.value.trainer_package_name, () => {
  if (form.value.trainer_package_name) onTrainerPackageChange()
})

onMounted(loadAll)
</script>

<template>
  <section class="model-update-page">
    <div class="page-header">
      <div>
        <p class="eyebrow">MODEL UPDATE</p>
        <h2>模型更新任务</h2>
        <p class="subline">训练插件作为普通插件上传；模型更新任务直接绑定目标模型、训练插件和数据源输入。</p>
      </div>
      <div class="header-actions">
        <button class="primary-btn" type="button" @click="resetForm">新建任务</button>
        <button class="ghost-btn" type="button" :disabled="loading" @click="loadAll">刷新</button>
        <button class="ghost-btn" type="button" :disabled="operating" @click="scanDueJobs">扫描到期任务</button>
      </div>
    </div>

    <p v-if="error" class="message error">{{ error }}</p>
    <p v-if="notice" class="message ok">{{ notice }}</p>

    <div class="scheduler-card">
      <span>调度器：{{ schedulerStatus?.running ? '运行中' : '未运行' }}</span>
      <span>间隔：{{ schedulerStatus?.interval_sec ?? '-' }} 秒</span>
      <span>最近扫描：{{ schedulerStatus?.last_scan_at || '-' }}</span>
      <button class="ghost-btn" type="button" @click="refreshScheduler">刷新状态</button>
    </div>

    <div class="content-grid">
      <aside class="panel job-list-panel">
        <div class="panel-title">
          <h3>任务列表</h3>
          <span>{{ jobs.length }} 项</span>
        </div>
        <div class="job-list">
          <button v-for="job in jobs" :key="job.id" type="button" class="job-item" :class="{ active: job.id === selectedJobId }" @click="selectJob(job)">
            <strong>{{ job.name }}</strong>
            <span>{{ job.trainer_package_name }}@{{ job.trainer_package_version }}</span>
            <em>{{ job.status }} · {{ job.next_run_at || '手动' }}</em>
          </button>
          <div v-if="!jobs.length && !loading" class="empty">暂无模型更新任务</div>
        </div>
      </aside>

      <main class="panel detail-panel">
        <div class="section-title">
          <h3>{{ form.id ? '编辑模型更新任务' : '新建模型更新任务' }}</h3>
          <div class="actions">
            <button class="primary-btn" type="button" :disabled="operating" @click="saveJob">保存</button>
            <button class="ghost-btn" type="button" :disabled="operating || !form.id" @click="runSelectedJob">立即执行</button>
            <button class="danger-btn" type="button" :disabled="operating || !form.id" @click="deleteSelectedJob">删除</button>
          </div>
        </div>

        <div class="form-grid">
          <label>
            <span>任务名称</span>
            <input v-model="form.name" />
          </label>
          <label>
            <span>目标模型</span>
            <select v-model="form.model_id">
              <option v-for="model in models" :key="model.id" :value="String(model.id)">
                {{ model.display_name }} · {{ model.family_fingerprint }}
              </option>
            </select>
          </label>
          <label>
            <span>训练插件包</span>
            <select v-model="form.trainer_package_name">
              <option v-for="item in packages" :key="item.id" :value="item.name">{{ item.display_name }} · {{ item.name }}</option>
            </select>
          </label>
          <label>
            <span>训练插件版本</span>
            <select v-model="form.trainer_package_version">
              <option v-for="item in trainerVersions" :key="item.id" :value="item.version">{{ item.version }}</option>
            </select>
          </label>
          <label>
            <span>运行周期（秒）</span>
            <input v-model.number="form.schedule_interval_sec" type="number" min="60" />
          </label>
          <label>
            <span>上线策略</span>
            <select v-model="form.promote_mode">
              <option value="manual">人工上线</option>
            </select>
          </label>
        </div>

        <label class="check-line">
          <input v-model="form.schedule_enabled" type="checkbox" />
          <span>启用定时模型更新</span>
        </label>

        <div class="fingerprint-box" v-if="selectedModel">
          <strong>目标模型指纹：</strong>{{ selectedModel.family_fingerprint }}
        </div>

        <div class="section-title compact">
          <h3>数据源输入绑定</h3>
          <div class="actions">
            <button class="ghost-btn" type="button" @click="addBinding('history')">添加历史窗口</button>
            <button class="ghost-btn" type="button" @click="addBinding('batch')">添加批量读取</button>
            <button class="ghost-btn" type="button" @click="addBinding('single')">添加单点读取</button>
          </div>
        </div>

        <div class="binding-list">
          <div v-for="(binding, index) in inputBindings" :key="index" class="binding-card">
            <div class="binding-head">
              <select v-model="binding.binding_type">
                <option value="history">历史窗口</option>
                <option value="batch">批量读取</option>
                <option value="single">单点读取</option>
              </select>
              <input v-model="binding.input_name" placeholder="插件输入名，如 training_window" />
              <select v-model.number="binding.data_source_id">
                <option v-for="source in dataSources" :key="source.id" :value="source.id">
                  {{ source.name }} · {{ source.connector_type }}
                </option>
              </select>
              <button class="danger-btn" type="button" @click="removeBinding(index)">移除</button>
            </div>

            <template v-if="binding.binding_type === 'single'">
              <input v-model="binding.source_tag" placeholder="读取位点 / Redis key / tag" />
            </template>

            <template v-else-if="binding.binding_type === 'batch'">
              <div class="binding-actions">
                <button class="ghost-btn" type="button" @click="addMapping(binding)">添加映射</button>
              </div>
              <div v-for="(mapping, mappingIndex) in binding.source_mappings" :key="mappingIndex" class="mapping-row">
                <input v-model="mapping.tag" placeholder="源位点" />
                <input v-model="mapping.key" placeholder="输入字段名" />
                <button class="danger-btn" type="button" @click="removeMapping(binding, mappingIndex)">删除</button>
              </div>
            </template>

            <template v-else>
              <div class="binding-actions">
                <button class="ghost-btn" type="button" @click="addSourceTag(binding)">添加历史位点</button>
              </div>
              <div v-for="(_tag, tagIndex) in binding.source_tags" :key="tagIndex" class="mapping-row">
                <input v-model="binding.source_tags![tagIndex]" placeholder="历史位点" />
                <button class="danger-btn" type="button" @click="removeSourceTag(binding, tagIndex)">删除</button>
              </div>
              <div class="window-grid">
                <label><span>起点偏移 min</span><input v-model.number="binding.window!.start_offset_min" type="number" /></label>
                <label><span>终点偏移 min</span><input v-model.number="binding.window!.end_offset_min" type="number" /></label>
                <label><span>采样间隔 sec</span><input v-model.number="binding.window!.sample_interval_sec" type="number" /></label>
                <label><span>前向回看 sec</span><input v-model.number="binding.window!.lookback_before_start_sec" type="number" /></label>
              </div>
            </template>
          </div>
          <div v-if="!inputBindings.length" class="empty">未配置输入绑定。训练插件将只能使用自身 fallback 数据。</div>
        </div>

        <label class="config-box">
          <span>训练配置 JSON</span>
          <textarea v-model="form.configText" rows="6" />
        </label>

        <div class="section-title compact">
          <h3>候选模型</h3>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th>版本</th>
              <th>状态</th>
              <th>R²</th>
              <th>MAE</th>
              <th>创建时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="candidate in candidates" :key="candidate.id">
              <td>{{ candidate.version }}</td>
              <td><span class="status-pill">{{ candidate.status }}</span></td>
              <td>{{ metricValue(candidate, 'r2') }}</td>
              <td>{{ metricValue(candidate, 'mae') }}</td>
              <td>{{ candidate.created_at }}</td>
              <td class="actions">
                <button class="primary-btn" type="button" :disabled="candidate.status === 'PROMOTED' || operating" @click="promoteCandidate(candidate)">上线</button>
                <button class="danger-btn" type="button" :disabled="candidate.status === 'PROMOTED' || candidate.status === 'REJECTED' || operating" @click="rejectCandidate(candidate)">驳回</button>
              </td>
            </tr>
            <tr v-if="!candidates.length"><td colspan="6" class="empty">暂无候选模型</td></tr>
          </tbody>
        </table>

        <div class="section-title compact">
          <h3>运行历史</h3>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th>状态</th>
              <th>插件 Run ID</th>
              <th>触发</th>
              <th>输入摘要</th>
              <th>开始时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="run in runs" :key="run.id">
              <td><span class="status-pill">{{ run.status }}</span></td>
              <td>{{ run.run_id || '-' }}</td>
              <td>{{ run.trigger_type }}</td>
              <td class="json-cell">{{ JSON.stringify(run.inputs) }}</td>
              <td>{{ run.started_at }}</td>
            </tr>
            <tr v-if="!runs.length"><td colspan="5" class="empty">暂无运行记录</td></tr>
          </tbody>
        </table>
      </main>
    </div>
  </section>
</template>

<style scoped>
.model-update-page { max-width: 1600px; margin: 0 auto; color: #d9f7ff; padding: 16px 24px 40px; box-sizing: border-box; }
.page-header, .scheduler-card { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 16px; padding: 16px 20px; border: 1px solid rgba(0,243,255,.28); background: rgba(2,18,38,.72); box-shadow: inset 0 0 22px rgba(0,243,255,.08); border-radius: 6px; }
.scheduler-card { justify-content: flex-start; flex-wrap: wrap; font-size: 12px; color: rgba(160,207,255,.82); }
.eyebrow { margin: 0 0 4px; color: #00f3ff; font-size: 11px; letter-spacing: .2em; }
h2, h3 { margin: 0; color: #fff; }
h2 { font-size: 20px; } h3 { font-size: 16px; }
.subline { margin: 6px 0 0; color: rgba(160,207,255,.76); font-size: 12px; line-height: 1.5; }
.header-actions, .actions, .binding-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.content-grid { display: grid; grid-template-columns: 300px minmax(0, 1fr); gap: 20px; align-items: start; }
.panel { border: 1px solid rgba(0,243,255,.24); background: rgba(3,13,28,.82); box-shadow: 0 8px 24px rgba(0,0,0,.28); padding: 16px; border-radius: 6px; box-sizing: border-box; }
.panel-title, .section-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px dashed rgba(0,243,255,.15); }
.section-title.compact { margin-top: 18px; }
.panel-title span { color: #00f3ff; font-size: 12px; background: rgba(0,243,255,.1); padding: 2px 6px; border-radius: 10px; }
.job-list { display: flex; flex-direction: column; gap: 8px; }
.job-item { text-align: left; border: 1px solid rgba(0,243,255,.12); background: rgba(0,243,255,.02); color: #d9f7ff; padding: 10px 12px; cursor: pointer; border-radius: 4px; }
.job-item.active { border-color: #00f3ff; background: rgba(0,243,255,.15); box-shadow: inset 2px 0 0 #00f3ff; }
.job-item strong, .job-item span, .job-item em { display: block; }
.job-item span { color: rgba(160,207,255,.62); font-size: 11px; margin-top: 3px; }
.job-item em { color: #00f3ff; font-style: normal; font-size: 11px; margin-top: 6px; }
.form-grid, .window-grid { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 12px; }
.window-grid { grid-template-columns: repeat(4, minmax(0,1fr)); margin-top: 10px; }
label span { display: block; color: rgba(160,207,255,.7); font-size: 12px; margin-bottom: 6px; }
input, select, textarea { width: 100%; box-sizing: border-box; border: 1px solid rgba(0,243,255,.24); background: rgba(1,10,18,.9); color: #d9f7ff; padding: 8px 10px; border-radius: 4px; }
textarea { font-family: "Courier New", monospace; }
.check-line { display: flex; align-items: center; gap: 8px; margin: 12px 0; }
.check-line input { width: auto; }
.fingerprint-box { border: 1px solid rgba(0,243,255,.18); background: rgba(0,243,255,.06); padding: 10px 12px; margin: 12px 0; font-size: 12px; color: #00f3ff; border-radius: 4px; }
.binding-list { display: flex; flex-direction: column; gap: 10px; }
.binding-card { border: 1px solid rgba(0,243,255,.16); background: rgba(0,243,255,.04); padding: 12px; border-radius: 4px; }
.binding-head, .mapping-row { display: grid; grid-template-columns: 140px minmax(0,1fr) minmax(0,1fr) auto; gap: 8px; align-items: center; margin-bottom: 8px; }
.mapping-row { grid-template-columns: minmax(0,1fr) minmax(0,1fr) auto; }
.config-box { display: block; margin-top: 16px; }
.data-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.data-table th, .data-table td { border-bottom: 1px solid rgba(0,243,255,.1); padding: 10px 8px; text-align: left; vertical-align: middle; }
.data-table th { color: #00f3ff; font-weight: normal; background: rgba(0,243,255,.03); }
.json-cell { max-width: 360px; word-break: break-all; color: rgba(160,207,255,.76); }
.status-pill { display: inline-flex; border: 1px solid rgba(0,243,255,.38); color: #00f3ff; padding: 2px 6px; font-size: 11px; border-radius: 2px; }
.primary-btn, .ghost-btn, .danger-btn { border: 1px solid #00f3ff; color: #00f3ff; background: rgba(0,243,255,.05); padding: 6px 12px; border-radius: 3px; cursor: pointer; text-decoration: none; font-size: 12px; white-space: nowrap; }
.primary-btn { background: #00f3ff; color: #04121f; font-weight: 600; }
.danger-btn { border-color: #ff4d4d; color: #ff4d4d; background: rgba(255,77,77,.05); }
button:disabled { opacity: .35; cursor: not-allowed; filter: grayscale(1); }
.message { border: 1px solid; padding: 8px 12px; margin: 0 0 16px; font-size: 12px; border-radius: 4px; }
.message.error { color: #ff6666; border-color: rgba(255,102,102,.35); background: rgba(255,102,102,.08); }
.message.ok { color: #00ffcc; border-color: rgba(0,255,204,.35); background: rgba(0,255,204,.08); }
.empty { color: rgba(160,207,255,.45); padding: 24px 12px; text-align: center; font-size: 12px; }
@media (max-width: 1080px) { .content-grid { grid-template-columns: 1fr; } .form-grid, .window-grid { grid-template-columns: 1fr; } .binding-head, .mapping-row { grid-template-columns: 1fr; } }
</style>
