import { apiFetch } from './client'

export interface ObservabilitySchedulerStatus {
  enabled: boolean
  mode: string
  thread_alive: boolean
  daemon_pid: number | null
  daemon_exit_code: number | null
  daemon_binary_path: string | null
  worker_id: string
  started_at: string | null
  started_age_sec: number | null
  last_error: string | null
  daemon_tick_interval_ms: number
  daemon_idle_min_interval_ms: number
  daemon_idle_max_interval_ms: number
  daemon_error_backoff_ms: number
  recovery_interval_sec: number
  runtime_observation?: Record<string, unknown>
}

export interface SchedulerLockRecord {
  key: string
  instance_id: number | null
  ttl_sec: number | null
}

export interface ObservabilityEventRecord {
  id: number
  event_type: string
  actor: string
  target_type: string
  target_id: string
  details: Record<string, unknown>
  created_at: string
}

export interface ScheduleRunRecord {
  run_id: string
  package_name: string
  version: string
  instance_id: number | null
  status: string
  started_at: string
  finished_at: string
  metrics: Record<string, unknown>
  error: Record<string, unknown>
}

export interface ScheduleRunStats {
  completed_24h: number
  failed_24h: number
  timed_out_24h: number
  skipped_24h: number
  partial_success_24h: number
}

export interface LicenseSnapshot {
  status: string
  valid: boolean
  readonly_mode: boolean
  message: string
  license_id?: string | null
  customer_name?: string | null
  issuer?: string | null
  key_id?: string | null
  grant_mode?: string | null
  issued_at?: string | null
  not_before?: string | null
  not_after?: string | null
}

export interface ObservabilitySummary {
  scheduler: ObservabilitySchedulerStatus
  locks: SchedulerLockRecord[]
  license: LicenseSnapshot
  recent_events: ObservabilityEventRecord[]
  recent_schedule_runs: ScheduleRunRecord[]
  schedule_run_stats: ScheduleRunStats
  generated_at: string
}

export async function getObservabilitySummary(): Promise<ObservabilitySummary> {
  return apiFetch<ObservabilitySummary>('/api/v1/observability/summary')
}
