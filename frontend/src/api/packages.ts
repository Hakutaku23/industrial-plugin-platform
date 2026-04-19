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
  connector_type: 'mock' | 'redis'
  config: Record<string, unknown>
  read_enabled: boolean
  write_enabled: boolean
  status: string
  created_at: string
  updated_at: string
}

export interface PluginInstanceRecord {
  id: number
  name: string
  package_id: number
  version_id: number
  package_name: string
  version: string
  input_bindings: Record<string, unknown>[]
  output_bindings: Record<string, unknown>[]
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
  const response = await fetch(`/api/v1/packages?filename=${encodeURIComponent(file.name)}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/octet-stream',
    },
    body: await file.arrayBuffer(),
  })

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(errorText || '插件包上传失败')
  }

  return response.json()
}

export async function listPackages(): Promise<PluginPackageSummary[]> {
  const response = await fetch('/api/v1/packages')
  if (!response.ok) {
    throw new Error((await response.text()) || '插件包列表加载失败')
  }

  const payload = await response.json()
  return payload.items
}

export async function listPackageVersions(packageName: string): Promise<PluginVersionRecord[]> {
  const response = await fetch(`/api/v1/packages/${encodeURIComponent(packageName)}/versions`)
  if (!response.ok) {
    throw new Error((await response.text()) || '插件版本加载失败')
  }

  const payload = await response.json()
  return payload.items
}

export async function deletePackage(packageName: string): Promise<void> {
  const response = await fetch(`/api/v1/packages/${encodeURIComponent(packageName)}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error((await response.text()) || '插件包删除失败')
  }
}

export async function runPackageVersion(
  packageName: string,
  version: string,
  inputs: Record<string, unknown>,
  config: Record<string, unknown> = {},
): Promise<RunPluginResult> {
  const response = await fetch(
    `/api/v1/packages/${encodeURIComponent(packageName)}/versions/${encodeURIComponent(version)}/runs`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ inputs, config }),
    },
  )
  if (!response.ok) {
    throw new Error((await response.text()) || '插件执行失败')
  }

  return response.json()
}

export async function listRuns(packageName?: string, instanceId?: number): Promise<PluginRunRecord[]> {
  const params = new URLSearchParams()
  if (packageName) {
    params.set('package_name', packageName)
  }
  if (instanceId !== undefined) {
    params.set('instance_id', String(instanceId))
  }
  const query = params.toString() ? `?${params.toString()}` : ''
  const response = await fetch(`/api/v1/runs${query}`)
  if (!response.ok) {
    throw new Error((await response.text()) || '运行记录加载失败')
  }

  const payload = await response.json()
  return payload.items
}

export async function listRunLogs(runId: string): Promise<RunLogRecord[]> {
  const response = await fetch(`/api/v1/runs/${encodeURIComponent(runId)}/logs`)
  if (!response.ok) {
    throw new Error((await response.text()) || '运行日志加载失败')
  }

  const payload = await response.json()
  return payload.items
}

export async function listWritebackRecords(runId?: string): Promise<WritebackRecord[]> {
  const query = runId ? `?run_id=${encodeURIComponent(runId)}` : ''
  const response = await fetch(`/api/v1/writeback-records${query}`)
  if (!response.ok) {
    throw new Error((await response.text()) || '写回记录加载失败')
  }

  const payload = await response.json()
  return payload.items
}

export async function listDataSources(): Promise<DataSourceRecord[]> {
  const response = await fetch('/api/v1/data-sources')
  if (!response.ok) {
    throw new Error((await response.text()) || '数据源列表加载失败')
  }

  const payload = await response.json()
  return payload.items
}

export async function saveDataSource(payload: {
  name: string
  connector_type: 'mock' | 'redis'
  config: Record<string, unknown>
  read_enabled: boolean
  write_enabled: boolean
}): Promise<{ id: number; name: string; connector_type: string; status: string }> {
  const response = await fetch('/api/v1/data-sources', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error((await response.text()) || '数据源保存失败')
  }

  return response.json()
}

export async function deleteDataSource(dataSourceId: number): Promise<void> {
  const response = await fetch(`/api/v1/data-sources/${dataSourceId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error((await response.text()) || '数据源删除失败')
  }
}

export async function listInstances(): Promise<PluginInstanceRecord[]> {
  const response = await fetch('/api/v1/instances')
  if (!response.ok) {
    throw new Error((await response.text()) || '实例列表加载失败')
  }

  const payload = await response.json()
  return payload.items
}

export async function saveInstance(payload: {
  id?: number | null
  name: string
  package_name: string
  version: string
  input_bindings: Record<string, unknown>[]
  output_bindings: Record<string, unknown>[]
  config: Record<string, unknown>
  writeback_enabled: boolean
  schedule_enabled: boolean
  schedule_interval_sec: number
}): Promise<{ id: number; name: string; status: string }> {
  const endpoint = payload.id ? `/api/v1/instances/${payload.id}` : '/api/v1/instances'
  const response = await fetch(endpoint, {
    method: payload.id ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error((await response.text()) || '实例保存失败')
  }

  return response.json()
}

export async function updateInstanceSchedule(
  instanceId: number,
  payload: { enabled: boolean; interval_sec?: number },
): Promise<PluginInstanceRecord> {
  const response = await fetch(`/api/v1/instances/${instanceId}/schedule`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error((await response.text()) || '实例定时状态更新失败')
  }

  return response.json()
}

export async function deleteInstance(instanceId: number): Promise<void> {
  const response = await fetch(`/api/v1/instances/${instanceId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error((await response.text()) || '实例删除失败')
  }
}

export async function runInstance(instanceId: number): Promise<RunPluginResult> {
  const response = await fetch(`/api/v1/instances/${instanceId}/runs`, {
    method: 'POST',
  })
  if (!response.ok) {
    throw new Error((await response.text()) || '实例运行失败')
  }

  return response.json()
}
