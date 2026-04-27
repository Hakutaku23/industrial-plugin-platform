import { apiFetch } from './client'

export interface ModelSummary {
  id: number
  model_name: string
  display_name: string
  description: string
  owner: string
  family_fingerprint: string
  status: string
  active_version_id: number | null
  active_version: string | null
  created_at: string
  updated_at: string
}

export interface ModelVersionRecord {
  id: number
  model_id: number
  model_name: string | null
  version: string
  artifact_dir: string
  manifest: Record<string, unknown>
  artifacts: Record<string, Record<string, unknown>>
  metrics: Record<string, unknown>
  checksums: Record<string, unknown>
  family_fingerprint: string
  metrics_completeness: Record<string, unknown>
  status: string
  source: string
  source_job_id: string | null
  created_at: string
  activated_at: string | null
  archived_at: string | null
}

export interface ModelBindingRecord {
  id: number
  instance_id: number
  model_id: number
  model_name: string | null
  model_version_id: number | null
  binding_mode: 'current' | 'fixed_version'
  family_fingerprint: string
  plugin_required_family_fingerprint?: string | null
  fingerprint_match?: boolean
  created_at: string
  updated_at: string
}

export interface InstanceModelRequirement {
  instance_id: number
  package_name: string
  version: string
  required: boolean
  family_fingerprint: string | null
  compatible_models: ModelSummary[]
  message: string
}

export async function listModels(): Promise<ModelSummary[]> {
  const payload = await apiFetch<{ items: ModelSummary[] }>('/api/v1/models')
  return payload.items
}

export async function getModel(modelId: number): Promise<ModelSummary> {
  return apiFetch<ModelSummary>(`/api/v1/models/${modelId}`)
}

export async function listModelVersions(modelId: number): Promise<ModelVersionRecord[]> {
  const payload = await apiFetch<{ items: ModelVersionRecord[] }>(`/api/v1/models/${modelId}/versions`)
  return payload.items
}

export async function validateModelVersion(modelId: number, versionId: number): Promise<ModelVersionRecord> {
  return apiFetch<ModelVersionRecord>(`/api/v1/models/${modelId}/versions/${versionId}/validate`, {
    method: 'POST',
  })
}

export async function promoteModelVersion(modelId: number, versionId: number, reason = 'manual promote'): Promise<ModelSummary> {
  return apiFetch<ModelSummary>(`/api/v1/models/${modelId}/versions/${versionId}/promote`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  })
}

export async function rollbackModel(modelId: number, reason = 'manual rollback'): Promise<ModelSummary> {
  return apiFetch<ModelSummary>(`/api/v1/models/${modelId}/rollback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  })
}

export async function getInstanceModelRequirement(instanceId: number): Promise<InstanceModelRequirement> {
  return apiFetch<InstanceModelRequirement>(`/api/v1/instances/${instanceId}/model-requirement`)
}

export async function bindInstanceModel(payload: {
  instanceId: number
  model_id: number
  binding_mode: 'current' | 'fixed_version'
  model_version_id?: number | null
}): Promise<ModelBindingRecord> {
  return apiFetch<ModelBindingRecord>(`/api/v1/instances/${payload.instanceId}/model-binding`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model_id: payload.model_id,
      binding_mode: payload.binding_mode,
      model_version_id: payload.model_version_id ?? null,
    }),
  })
}

export async function getInstanceModelBinding(instanceId: number): Promise<ModelBindingRecord> {
  return apiFetch<ModelBindingRecord>(`/api/v1/instances/${instanceId}/model-binding`)
}

export async function deleteInstanceModelBinding(instanceId: number): Promise<void> {
  await apiFetch(`/api/v1/instances/${instanceId}/model-binding`, { method: 'DELETE' })
}
