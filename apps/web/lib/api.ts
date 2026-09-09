/**
 * Server-side client for the FastAPI service.
 *
 * `API_BASE_URL` is deliberately not `NEXT_PUBLIC_`: every call to the API
 * goes through a server component or a route handler, so no API credential
 * ever reaches the browser bundle. See rule 7 in CLAUDE.md.
 */

export const API_BASE_URL = process.env.API_BASE_URL ?? 'http://localhost:8000'

export function apiUrl(path: string): string {
  const base = API_BASE_URL.replace(/\/+$/, '')
  const suffix = path.startsWith('/') ? path : `/${path}`
  return `${base}${suffix}`
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: { 'content-type': 'application/json', ...init?.headers },
    cache: 'no-store',
  })

  if (!response.ok) {
    throw new ApiError(`${init?.method ?? 'GET'} ${path} failed`, response.status)
  }

  return (await response.json()) as T
}
