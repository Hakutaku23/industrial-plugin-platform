import { apiFetch } from './client'

export type SystemSettingsPayload = Record<string, any>

export interface SettingCatalogItem {
  path: string
  label: string
  description: string
  type: string
  editable: boolean
  minimum?: number | null
  maximum?: number | null
  value: unknown
}

export interface SystemSettingsResponse {
  settings: SystemSettingsPayload
  catalog: {
    settings_file: string
    items: SettingCatalogItem[]
  }
}

export interface MaintenanceStatus {
  run_directory_cleanup: Record<string, unknown> | null
  database_cleanup: Record<string, unknown> | null
}

export async function getSystemSettings(): Promise<SystemSettingsResponse> {
  return apiFetch<SystemSettingsResponse>('/api/v1/system-settings')
}

export async function updateSystemSettings(settings: SystemSettingsPayload): Promise<SystemSettingsResponse> {
  return apiFetch<SystemSettingsResponse>('/api/v1/system-settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ settings }),
  })
}

export async function getMaintenanceStatus(): Promise<MaintenanceStatus> {
  return apiFetch<MaintenanceStatus>('/api/v1/system-settings/maintenance/status')
}

export async function runRunDirectoryCleanup(dryRun?: boolean): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>('/api/v1/system-settings/maintenance/run-directory-cleanup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dry_run: dryRun ?? null }),
  })
}

export async function runDatabaseCleanup(dryRun?: boolean): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>('/api/v1/system-settings/maintenance/database-cleanup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dry_run: dryRun ?? null }),
  })
}
