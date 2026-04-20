export class ApiError extends Error {
  status: number
  payload: unknown

  constructor(status: number, message: string, payload: unknown) {
    super(message)
    this.status = status
    this.payload = payload
  }
}

async function parseResponse(response: Response): Promise<unknown> {
  if (response.status === 204 || response.status === 205) {
    return null
  }

  const body = await response.text()
  if (!body) {
    return null
  }

  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return JSON.parse(body)
  }
  return body
}

export async function apiFetch<T>(input: RequestInfo | URL, init: RequestInit = {}): Promise<T> {
  const response = await fetch(input, {
    ...init,
    credentials: 'include',
    headers: {
      ...(init.headers || {}),
    },
  })

  const payload = await parseResponse(response)
  if (!response.ok) {
    if (response.status === 401 && window.location.pathname !== '/login') {
      const redirect = `${window.location.pathname}${window.location.search}${window.location.hash}`
      window.location.assign(`/login?redirect=${encodeURIComponent(redirect)}`)
    }
    const message =
      typeof payload === 'string'
        ? payload
        : typeof payload === 'object' && payload !== null && 'detail' in payload
          ? String((payload as { detail: unknown }).detail)
          : `Request failed with status ${response.status}`
    throw new ApiError(response.status, message, payload)
  }

  return payload as T
}
