import { apiFetch } from './client'

export interface ArtifactCheck {
  required_artifacts: string[]
  artifact_keys: string[]
  missing_required_keys: string[]
  missing_files: string[]
  present_files: string[]
  artifact_dir: string | null
}

export interface ModelBindingHealthRecord {
  instance_id: number
  instance_name: string | null
  package_name: string | null
  plugin_version: string | null
  plugin_model_required: boolean
  plugin_family_fingerprint: string | null
  required_artifacts: string[]
  status: string
  severity: 'ok' | 'info' | 'warning' | 'error' | string
  message: string
  binding: Record<string, unknown> | null
  model: Record<string, unknown> | null
  version: Record<string, unknown> | null
  artifact_check: ArtifactCheck
}

export interface ModelBindingHealthPayload {
  items: ModelBindingHealthRecord[]
  summary: Record<string, number>
  severity_summary: Record<string, number>
  total: number
}

export interface RunDiagnosticsPayload {
  run: Record<string, unknown>
  model_metrics: Record<string, unknown>
  model_binding_health: ModelBindingHealthRecord | Record<string, unknown> | null
  writeback_summary: Record<string, unknown>
  writebacks: Record<string, unknown>[]
  logs: Record<string, unknown>[]
  suggestions: Array<{ level: string; code: string; message: string }>
}

export async function listModelBindingHealth(): Promise<ModelBindingHealthPayload> {
  return apiFetch<ModelBindingHealthPayload>('/api/v1/runtime-diagnostics/model-bindings')
}

export async function getInstanceModelBindingDiagnostics(instanceId: number): Promise<ModelBindingHealthRecord> {
  return apiFetch<ModelBindingHealthRecord>(`/api/v1/instances/${instanceId}/model-binding/diagnostics`)
}

export async function getRunDiagnostics(runId: string): Promise<RunDiagnosticsPayload> {
  return apiFetch<RunDiagnosticsPayload>(`/api/v1/runs/${encodeURIComponent(runId)}/diagnostics`)
}
