import { apiFetch } from './client'

export interface UploadPackageResult {
  package_id: number
  version_id: number
  audit_event_id: number
  name: string
  version: string
  status: string
  digest: string
  package_dir: string
}

export interface PluginPackageSummary {
  id: number
  name: string
  display_name: string
  description: string
  status: string
  version_count: number
  latest_version: string | null
  latest_version_id: number | null
  latest_digest: string | null
  created_at: string
  updated_at: string
  latest_updated_at: string | null
}

export interface PluginVersionRecord {
  id: number
  package_id: number
  package_name: string
  version: string
  digest: string
  package_path: string
  status: string
  manifest: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface PluginRunRecord {
  id: number
  run_id: string
  package_id: number
  version_id: number
  instance_id: number | null
  package_name: string
  version: string
  trigger_type: string
  environment: string
  status: string
  attempt: number
  inputs: Record<string, unknown>
  outputs: Record<string, unknown>
  metrics: Record<string, unknown>
  error: Record<string, unknown>
  created_at: string
  started_at: string
  finished_at: string
}

export interface RunLogRecord {
  id: number
  run_id: string
  source: string
  level: string
  message: string
  created_at: string
}

export interface WritebackRecord {
  id: number
  run_id: string
  output_name: string
  data_source_id: number
  target_tag: string
  value: unknown
  status: string
  reason: string
  dry_run: boolean
  created_at: string
}

export interface DataSourceRecord {
  id: number
  name: string
  connector_type: 'mock' | 'redis' | 'tdengine'
  config: Record<string, unknown>
  read_enabled: boolean
  write_enabled: boolean
  status: string
  created_at: string
  updated_at: string
}

export interface DataSourceSavePayload {
  name: string
  connector_type: 'mock' | 'redis' | 'tdengine'
  config: Record<string, unknown>
  read_enabled: boolean
  write_enabled: boolean
}

export type BindingType = 'single' | 'batch'
export type InputBatchOutputFormat = 'named-map' | 'ordered-list'

export interface SingleInputBinding {
  binding_type?: 'single'
  input_name: string
  data_source_id: number
  source_tag: string
}

export interface BatchInputSourceMapping {
  tag: string
  key: string
}

export interface BatchInputBinding {
  binding_type: 'batch'
  input_name?: string
  data_source_id: number
  source_tags?: string[]
  source_mappings?: BatchInputSourceMapping[]
  output_format?: InputBatchOutputFormat
}

export type InputBinding = SingleInputBinding | BatchInputBinding

export interface SingleOutputBinding {
  binding_type?: 'single'
  output_name: string
  data_source_id: number
  target_tag: string
  dry_run?: boolean
}

export interface BatchOutputBinding {
  binding_type: 'batch'
  output_name: string
  data_source_id: number
  target_tags: string[]
  dry_run?: boolean
}

export type OutputBinding = SingleOutputBinding | BatchOutputBinding

export interface PluginInstanceRecord {
  id: number
  name: string
  package_id: number
  version_id: number
  package_name: string
  version: string
  input_bindings: InputBinding[]
  output_bindings: OutputBinding[]
  config: Record<string, unknown>
  writeback_enabled: boolean
  schedule_enabled: boolean
  schedule_interval_sec: number
  last_scheduled_run_at: string | null
  next_scheduled_run_at: string | null
  status: string
  created_at: string
  updated_at: string
}

export interface RunPluginResult {
  id: number
  run_id: string
  status: string
  outputs: Record<string, unknown>
  metrics: Record<string, unknown>
  error: Record<string, unknown>
  inputs?: Record<string, unknown>
  writeback?: Record<string, unknown>[]
}

export async function uploadPackage(file: File): Promise<UploadPackageResult> {
  return apiFetch<UploadPackageResult>(`/api/v1/packages?filename=${encodeURIComponent(file.name)}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/octet-stream',
    },
    body: await file.arrayBuffer(),
  })
}

export async function listPackages(): Promise<PluginPackageSummary[]> {
  const payload = await apiFetch<{ items: PluginPackageSummary[] }>('/api/v1/packages')
  return payload.items
}

export async function listPackageVersions(packageName: string): Promise<PluginVersionRecord[]> {
  const payload = await apiFetch<{ items: PluginVersionRecord[] }>(`/api/v1/packages/${encodeURIComponent(packageName)}/versions`)
  return payload.items
}

export async function deletePackage(packageName: string): Promise<void> {
  await apiFetch(`/api/v1/packages/${encodeURIComponent(packageName)}`, {
    method: 'DELETE',
  })
}

export async function runPackageVersion(
  packageName: string,
  version: string,
  inputs: Record<string, unknown>,
  config: Record<string, unknown> = {},
): Promise<RunPluginResult> {
  return apiFetch<RunPluginResult>(
    `/api/v1/packages/${encodeURIComponent(packageName)}/versions/${encodeURIComponent(version)}/runs`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ inputs, config }),
    },
  )
}

export async function listRuns(packageName?: string, instanceId?: number): Promise<PluginRunRecord[]> {
  const params = new URLSearchParams()
  if (packageName) params.set('package_name', packageName)
  if (instanceId !== undefined) params.set('instance_id', String(instanceId))
  const query = params.toString() ? `?${params.toString()}` : ''
  const payload = await apiFetch<{ items: PluginRunRecord[] }>(`/api/v1/runs${query}`)
  return payload.items
}

export async function listRunLogs(runId: string): Promise<RunLogRecord[]> {
  const payload = await apiFetch<{ items: RunLogRecord[] }>(`/api/v1/runs/${encodeURIComponent(runId)}/logs`)
  return payload.items
}

export async function listWritebackRecords(runId?: string): Promise<WritebackRecord[]> {
  const query = runId ? `?run_id=${encodeURIComponent(runId)}` : ''
  const payload = await apiFetch<{ items: WritebackRecord[] }>(`/api/v1/writeback-records${query}`)
  return payload.items
}

export async function listDataSources(): Promise<DataSourceRecord[]> {
  const payload = await apiFetch<{ items: DataSourceRecord[] }>('/api/v1/data-sources')
  return payload.items
}

export async function saveDataSource(
  payload: DataSourceSavePayload,
): Promise<{ id: number; name: string; connector_type: string; status: string }> {
  return apiFetch('/api/v1/data-sources', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function updateDataSource(
  dataSourceId: number,
  payload: DataSourceSavePayload,
): Promise<{ id: number; name: string; connector_type: string; status: string }> {
  return apiFetch(`/api/v1/data-sources/${dataSourceId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function deleteDataSource(dataSourceId: number): Promise<void> {
  await apiFetch(`/api/v1/data-sources/${dataSourceId}`, {
    method: 'DELETE',
  })
}

export async function listInstances(): Promise<PluginInstanceRecord[]> {
  const payload = await apiFetch<{ items: PluginInstanceRecord[] }>('/api/v1/instances')
  return payload.items
}

export async function saveInstance(payload: {
  id?: number | null
  name: string
  package_name: string
  version: string
  input_bindings: InputBinding[]
  output_bindings: OutputBinding[]
  config: Record<string, unknown>
  writeback_enabled: boolean
  schedule_enabled: boolean
  schedule_interval_sec: number
}): Promise<{ id: number; name: string; status: string }> {
  const endpoint = payload.id ? `/api/v1/instances/${payload.id}` : '/api/v1/instances'
  return apiFetch(endpoint, {
    method: payload.id ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function updateInstanceSchedule(
  instanceId: number,
  payload: { enabled: boolean; interval_sec?: number },
): Promise<PluginInstanceRecord> {
  return apiFetch<PluginInstanceRecord>(`/api/v1/instances/${instanceId}/schedule`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function deleteInstance(instanceId: number): Promise<void> {
  await apiFetch(`/api/v1/instances/${instanceId}`, {
    method: 'DELETE',
  })
}

export async function runInstance(instanceId: number): Promise<RunPluginResult> {
  return apiFetch<RunPluginResult>(`/api/v1/instances/${instanceId}/runs`, {
    method: 'POST',
  })
}
