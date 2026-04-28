import { apiFetch } from './client'

export type BindingType = 'single' | 'batch' | 'history'
export type BatchOutputFormat = 'named-map' | 'ordered-list'

export interface HistoryWindowConfig {
  start_offset_min: number
  end_offset_min: number
  sample_interval_sec: number
  lookback_before_start_sec: number
  fill_method: 'ffill' | 'interpolate' | 'ffill_then_interpolate' | 'none'
  strict_first_value: boolean
}

export interface SourceMappingRow {
  tag: string
  key: string
}

export interface ModelUpdateInputBinding {
  binding_type: BindingType
  input_name?: string
  data_source_id: number
  source_tag?: string
  source_tags?: string[]
  source_mappings?: SourceMappingRow[]
  output_format?: BatchOutputFormat
  window?: HistoryWindowConfig
}

export interface ModelUpdateJob {
  id: number
  name: string
  model_id: number
  trainer_package_name: string
  trainer_package_version: string
  trainer_instance_id?: number | null
  input_bindings: ModelUpdateInputBinding[]
  schedule_enabled: boolean
  schedule_interval_sec: number
  promote_mode: string
  metric_policy: Record<string, unknown>
  config: Record<string, unknown>
  status: string
  last_run_at: string | null
  next_run_at: string | null
  created_at: string
  updated_at: string
}

export interface ModelUpdateRun {
  id: number
  job_id: number
  run_id: string | null
  status: string
  trigger_type: string
  current_model_version_id: number | null
  candidate_id: number | null
  inputs: Record<string, unknown>
  metrics: Record<string, unknown>
  error: Record<string, unknown>
  started_at: string
  finished_at: string | null
}

export interface ModelUpdateCandidate {
  id: number
  job_id: number
  run_id: string | null
  model_id: number
  version: string
  version_id: number | null
  candidate_dir: string
  manifest: Record<string, unknown>
  artifacts: Record<string, unknown>
  metrics: Record<string, unknown>
  status: string
  reason: string
  created_at: string
  validated_at: string | null
  promoted_at: string | null
  rejected_at: string | null
}

export interface ModelUpdateSchedulerStatus {
  enabled: boolean
  running: boolean
  started_at: string | null
  last_scan_at: string | null
  last_result: Record<string, unknown> | null
  interval_sec: number
  max_due_batch: number
}

export async function listModelUpdateJobs(): Promise<ModelUpdateJob[]> {
  const payload = await apiFetch<{ items: ModelUpdateJob[] }>('/api/v1/model-update-jobs')
  return payload.items
}

export async function createModelUpdateJob(payload: {
  name: string
  model_id: number
  trainer_package_name: string
  trainer_package_version: string
  input_bindings: ModelUpdateInputBinding[]
  schedule_enabled: boolean
  schedule_interval_sec: number
  promote_mode: string
  metric_policy?: Record<string, unknown>
  config?: Record<string, unknown>
}): Promise<ModelUpdateJob> {
  return apiFetch<ModelUpdateJob>('/api/v1/model-update-jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function updateModelUpdateJob(jobId: number, payload: Partial<ModelUpdateJob>): Promise<ModelUpdateJob> {
  return apiFetch<ModelUpdateJob>(`/api/v1/model-update-jobs/${jobId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function deleteModelUpdateJob(jobId: number): Promise<void> {
  await apiFetch(`/api/v1/model-update-jobs/${jobId}`, { method: 'DELETE' })
}

export async function runModelUpdateJob(jobId: number): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>(`/api/v1/model-update-jobs/${jobId}/run`, { method: 'POST' })
}

export async function listModelUpdateRuns(jobId: number): Promise<ModelUpdateRun[]> {
  const payload = await apiFetch<{ items: ModelUpdateRun[] }>(`/api/v1/model-update-jobs/${jobId}/runs`)
  return payload.items
}

export async function listModelUpdateCandidates(jobId: number): Promise<ModelUpdateCandidate[]> {
  const payload = await apiFetch<{ items: ModelUpdateCandidate[] }>(`/api/v1/model-update-jobs/${jobId}/candidates`)
  return payload.items
}

export async function promoteModelUpdateCandidate(candidateId: number, reason = 'manual promote candidate'): Promise<ModelUpdateCandidate> {
  return apiFetch<ModelUpdateCandidate>(`/api/v1/model-update-candidates/${candidateId}/promote`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  })
}

export async function rejectModelUpdateCandidate(candidateId: number, reason = 'manual reject candidate'): Promise<ModelUpdateCandidate> {
  return apiFetch<ModelUpdateCandidate>(`/api/v1/model-update-candidates/${candidateId}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  })
}

export async function getModelUpdateSchedulerStatus(): Promise<ModelUpdateSchedulerStatus> {
  return apiFetch<ModelUpdateSchedulerStatus>('/api/v1/model-update-scheduler/status')
}

export async function runDueModelUpdateJobs(): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>('/api/v1/model-update-scheduler/run-due', { method: 'POST' })
}
