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
    throw new Error(await response.text() || '插件包列表加载失败')
  }

  const payload = await response.json()
  return payload.items
}

export async function listPackageVersions(packageName: string): Promise<PluginVersionRecord[]> {
  const response = await fetch(`/api/v1/packages/${encodeURIComponent(packageName)}/versions`)
  if (!response.ok) {
    throw new Error(await response.text() || '插件版本加载失败')
  }

  const payload = await response.json()
  return payload.items
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
    throw new Error(await response.text() || '插件执行失败')
  }

  return response.json()
}

export async function listRuns(packageName?: string): Promise<PluginRunRecord[]> {
  const query = packageName ? `?package_name=${encodeURIComponent(packageName)}` : ''
  const response = await fetch(`/api/v1/runs${query}`)
  if (!response.ok) {
    throw new Error(await response.text() || '运行记录加载失败')
  }

  const payload = await response.json()
  return payload.items
}

export async function listDataSources(): Promise<DataSourceRecord[]> {
  const response = await fetch('/api/v1/data-sources')
  if (!response.ok) {
    throw new Error(await response.text() || '数据源列表加载失败')
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
    throw new Error(await response.text() || '数据源保存失败')
  }

  return response.json()
}

export async function listInstances(): Promise<PluginInstanceRecord[]> {
  const response = await fetch('/api/v1/instances')
  if (!response.ok) {
    throw new Error(await response.text() || '实例列表加载失败')
  }

  const payload = await response.json()
  return payload.items
}

export async function saveInstance(payload: {
  name: string
  package_name: string
  version: string
  input_bindings: Record<string, unknown>[]
  output_bindings: Record<string, unknown>[]
  config: Record<string, unknown>
  writeback_enabled: boolean
}): Promise<{ id: number; name: string; status: string }> {
  const response = await fetch('/api/v1/instances', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(await response.text() || '实例保存失败')
  }

  return response.json()
}

export async function runInstance(instanceId: number): Promise<RunPluginResult> {
  const response = await fetch(`/api/v1/instances/${instanceId}/runs`, {
    method: 'POST',
  })
  if (!response.ok) {
    throw new Error(await response.text() || '实例运行失败')
  }

  return response.json()
}
