export interface AppHttpConfig {
  baseURL?: string
  /** 设为 true 时，401/403 响应不触发跳转登录页，直接抛出错误（用于认证类接口自行处理错误） */
  noRedirectOn401?: boolean
}

const defaultConfig: AppHttpConfig = {
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
}

function getAppToken(): string | null {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem('app_access_token')
}

async function request<T>(url: string, init: RequestInit = {}, config: AppHttpConfig = {}): Promise<T> {
  const finalConfig = { ...defaultConfig, ...config }
  const baseURL = finalConfig.baseURL ?? ''
  const token = getAppToken()

  const headers: HeadersInit = {
    ...(init.headers ?? {}),
  }

  // 仅在 body 不是 FormData 时默认使用 application/json
  const isFormData =
    typeof FormData !== 'undefined' && init.body != null && init.body instanceof FormData
  if (!isFormData && (init.method === 'POST' || init.method === 'PUT' || init.method === 'PATCH')) {
    ;(headers as Record<string, string>)['Content-Type'] =
      (headers as Record<string, string>)['Content-Type'] ?? 'application/json'
  }

  if (token) {
    ;(headers as Record<string, string>)['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(baseURL + url, {
    ...init,
    headers,
  })

  if (response.status === 401 || response.status === 403) {
    // 有 token 且未禁用重定向 → session 过期，跳登录页
    // 无 token 或设置了 noRedirectOn401 → 认证端点业务错误（如密码错误），直接抛出由调用方处理
    if (token && typeof window !== 'undefined' && !finalConfig.noRedirectOn401) {
      try {
        const { ElMessage } = await import('element-plus')
        ElMessage.error('登录已过期或未授权，请重新登录')
      } catch {
        // ElementPlus 未加载时忽略
      }
      const redirect = encodeURIComponent(window.location.pathname + window.location.search)
      window.location.href = `/app/login?redirect=${redirect}`
      throw new Error('未授权访问用户端接口')
    }
    const text = await response.text().catch(() => '')
    throw new Error(text || `请求失败，状态码 ${response.status}`)
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

export const appHttp = {
  get: <T>(url: string, config?: AppHttpConfig) => request<T>(url, { method: 'GET' }, config),
  post: <T>(url: string, body?: unknown, config?: AppHttpConfig) =>
    request<T>(
      url,
      {
        method: 'POST',
        body:
          body != null
            ? typeof FormData !== 'undefined' && body instanceof FormData
              ? (body as FormData)
              : JSON.stringify(body)
            : undefined,
      },
      config,
    ),
  put: <T>(url: string, body?: unknown, config?: AppHttpConfig) =>
    request<T>(
      url,
      {
        method: 'PUT',
        body:
          body != null
            ? typeof FormData !== 'undefined' && body instanceof FormData
              ? (body as FormData)
              : JSON.stringify(body)
            : undefined,
      },
      config,
    ),
  patch: <T>(url: string, body?: unknown, config?: AppHttpConfig) =>
    request<T>(
      url,
      {
        method: 'PATCH',
        body:
          body != null
            ? typeof FormData !== 'undefined' && body instanceof FormData
              ? (body as FormData)
              : JSON.stringify(body)
            : undefined,
      },
      config,
    ),
  delete: <T>(url: string, config?: AppHttpConfig) => request<T>(url, { method: 'DELETE' }, config),
}

