import { apiFetch } from './client'

export interface SecurityStatus {
  enabled: boolean
  auth_mode: string
  session_cookie_name: string
}

export interface AuthMeResponse {
  authenticated: boolean
  security_enabled: boolean
  user: null | {
    id: number | null
    username: string
    display_name: string
    email: string | null
    roles: string[]
    permissions: string[]
  }
}

export interface RoleRecord {
  id: number
  name: string
  description: string
  is_system: boolean
  permissions: string[]
}

export interface UserRecord {
  id: number
  username: string
  display_name: string
  email: string | null
  status: string
  auth_source: string
  last_login_at: string | null
  created_at: string
  updated_at: string
  roles: string[]
  permissions: string[]
}

export async function getSecurityStatus(): Promise<SecurityStatus> {
  return apiFetch<SecurityStatus>('/api/v1/security/status')
}

export async function getMe(): Promise<AuthMeResponse> {
  return apiFetch<AuthMeResponse>('/api/v1/auth/me')
}

export async function login(username: string, password: string): Promise<{ ok: boolean }> {
  return apiFetch('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
}

export async function logout(): Promise<{ ok: boolean }> {
  return apiFetch('/api/v1/auth/logout', {
    method: 'POST',
  })
}

export async function listRoles(): Promise<RoleRecord[]> {
  const payload = await apiFetch<{ items: RoleRecord[] }>('/api/v1/roles')
  return payload.items
}

export async function listUsers(): Promise<UserRecord[]> {
  const payload = await apiFetch<{ items: UserRecord[] }>('/api/v1/users')
  return payload.items
}

export async function createUser(payload: {
  username: string
  display_name: string
  email: string | null
  password: string
  roles: string[]
}): Promise<UserRecord> {
  return apiFetch<UserRecord>('/api/v1/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function updateUser(
  userId: number,
  payload: { display_name?: string; email?: string | null; password?: string; status?: string },
): Promise<UserRecord> {
  return apiFetch<UserRecord>(`/api/v1/users/${userId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function assignUserRoles(userId: number, roles: string[]): Promise<UserRecord> {
  return apiFetch<UserRecord>(`/api/v1/users/${userId}/roles`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ roles }),
  })
}
