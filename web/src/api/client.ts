// 请求封装：统一处理 {ok, data, error} 返回格式，错误提示用后端给的中文
export interface ApiError {
  code: string
  message: string
  detail: Record<string, unknown>
}

export interface ApiResponse<T> {
  ok: boolean
  data: T | null
  error: ApiError | null
}

export class RequestError extends Error {
  code: string
  detail: Record<string, unknown>
  constructor(code: string, message: string, detail: Record<string, unknown> = {}) {
    super(message)
    this.code = code
    this.detail = detail
  }

  /** 规则校验返回的全部问题（中文） */
  get problems(): string[] {
    const p = this.detail.problems
    return Array.isArray(p) ? p.map(String) : []
  }
}

let csrfToken = ''
export function setCsrfToken(token: string) {
  csrfToken = token
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('X-Avalon-Client', 'web')
  if (csrfToken && !['GET', 'HEAD'].includes(init.method?.toUpperCase() ?? 'GET')) {
    headers.set('X-CSRF-Token', csrfToken)
  }
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  let resp: Response
  try {
    resp = await fetch(path, { ...init, headers, credentials: 'same-origin', cache: 'no-store' })
  } catch {
    throw new RequestError('logic_unavailable', '连不上后端，请检查 API 后端是否已启动')
  }
  let body: ApiResponse<T>
  try {
    body = (await resp.json()) as ApiResponse<T>
  } catch {
    throw new RequestError('internal', `后端返回了无法识别的内容（状态码 ${resp.status}）`)
  }
  if (!body.ok) {
    if (resp.status === 401 && !['/api/v1/auth/login', '/api/v1/auth/me'].includes(path)) {
      window.dispatchEvent(new Event('avalon:unauthorized'))
    }
    throw new RequestError(body.error?.code ?? 'internal', body.error?.message ?? '请求失败', body.error?.detail ?? {})
  }
  return body.data as T
}
