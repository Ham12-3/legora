/**
 * Browser-side API access. Everything goes through /api/proxy, which attaches
 * the internal token server-side. No credential ever lives in the bundle.
 */

import { ApiError } from '@/lib/api'

export async function clientApi<T>(path: string, init?: RequestInit): Promise<T> {
  const suffix = path.startsWith('/') ? path : `/${path}`
  const response = await fetch(`/api/proxy${suffix}`, {
    ...init,
    headers: { 'content-type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    let detail = `${init?.method ?? 'GET'} ${path} failed`
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // non-JSON error body
    }
    throw new ApiError(detail, response.status)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}
