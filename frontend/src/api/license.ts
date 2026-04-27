import { apiFetch } from './client'

export interface FingerprintPayload {
  installation_id: string
  machine_id?: string | null
  hostname?: string | null
  deployment_fingerprint: string
  generated_at: string
}

export interface LicenseSnapshot {
  status: string
  valid: boolean
  readonly_mode: boolean
  message: string
  license_file_path?: string | null
  public_keys_file_path?: string | null
  revocations_file_path?: string | null
  fingerprint?: string | null
  installation_id?: string | null
  issuer?: string | null
  key_id?: string | null
  license_id?: string | null
  customer_name?: string | null
  grant_mode?: string | null
  issued_at?: string | null
  not_before?: string | null
  not_after?: string | null
  grace_days?: number | null
  grace_expires_at?: string | null
  revoked?: boolean
  entitlements?: Record<string, unknown>
}

export interface LicenseRevocations {
  path: string
  revoked_license_ids: string[]
  updated_at?: string
  schema_version?: number
}

export async function getLicenseStatus(): Promise<LicenseSnapshot> {
  return apiFetch<LicenseSnapshot>('/api/v1/license/status')
}

export async function getLicenseFingerprint(): Promise<FingerprintPayload> {
  return apiFetch<FingerprintPayload>('/api/v1/license/fingerprint')
}

export async function getLicenseRevocations(): Promise<LicenseRevocations> {
  return apiFetch<LicenseRevocations>('/api/v1/license/revocations')
}

export async function uploadLicense(file: File): Promise<LicenseSnapshot> {
  return apiFetch<LicenseSnapshot>('/api/v1/license', {
    method: 'POST',
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
    body: await file.text(),
  })
}
