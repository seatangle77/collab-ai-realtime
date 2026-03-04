export interface HttpConfig {
  baseURL?: string
}

const defaultConfig: HttpConfig = {
  baseURL: 'http://localhost:8000',
}

function getAdminToken(): string | null {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem('admin_api_key')
}

async function request<T>(url: string, init: RequestInit = {}, config: HttpConfig = {}): Promise<T> {
  const finalConfig = { ...defaultConfig, ...config }
  const baseURL = finalConfig.baseURL ?? ''
  const token = getAdminToken()

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(init.headers ?? {}),
  }

  if (token) {
    ;(headers as Record<string, string>)['X-Admin-Token'] = token
  }

  const response = await fetch(baseURL + url, {
    ...init,
    headers,
  })

  if (response.status === 401 || response.status === 403) {
    if (typeof window !== 'undefined') {
      window.location.href = '/admin/login'
    }
    throw new Error('未授权访问后台接口')
  }

  if (!response.ok) {
    const text = await response.text().catch(() => '')
    throw new Error(text || `请求失败，状态码 ${response.status}`)
  }

  if (response.status === 204) {
    return undefined as unknown as T
  }

  return (await response.json()) as T
}

export const http = {
  get: <T>(url: string, config?: HttpConfig) => request<T>(url, { method: 'GET' }, config),
  post: <T>(url: string, body?: unknown, config?: HttpConfig) =>
    request<T>(
      url,
      {
        method: 'POST',
        body: body != null ? JSON.stringify(body) : undefined,
      },
      config,
    ),
  patch: <T>(url: string, body?: unknown, config?: HttpConfig) =>
    request<T>(
      url,
      {
        method: 'PATCH',
        body: body != null ? JSON.stringify(body) : undefined,
      },
      config,
    ),
  delete: <T>(url: string, config?: HttpConfig) => request<T>(url, { method: 'DELETE' }, config),
}

