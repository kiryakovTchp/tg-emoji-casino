const DEFAULT_API_ORIGIN =
  process.env.NEXT_PUBLIC_CASINO_API_BASE || "https://casino.gnezdoai.ru/api"

export const CRASH_API_BASE =
  process.env.NEXT_PUBLIC_CRASH_API_BASE || `${DEFAULT_API_ORIGIN}/crash`

export const TELEGRAM_AUTH_URL = `${DEFAULT_API_ORIGIN}/auth/telegram`

export interface CrashApiResponse<T = any> {
  data?: T
  ok?: boolean
  success?: boolean
  error?: string
}

export async function crashApiFetch<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
  baseUrl?: string
): Promise<T> {
  const resolvedBase = baseUrl || CRASH_API_BASE
  const url = path.startsWith("http") ? path : `${resolvedBase}${path}`
  const headers = new Headers(options.headers || {})

  if (token) {
    headers.set("Authorization", `Bearer ${token}`)
  }

  const isFormData = options.body instanceof FormData
  if (options.body && !isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }

  const response = await fetch(url, {
    ...options,
    headers,
  })

  if (!response.ok) {
    const errorText = await response.text().catch(() => "")
    throw new Error(
      `Crash API ${response.status}: ${errorText || response.statusText}`
    )
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}
