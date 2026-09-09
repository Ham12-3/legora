import 'server-only'

import { cache } from 'react'
import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

import { auth } from '@/auth'
import { ApiError, apiUrl } from '@/lib/api'
import { INTERNAL_API_SECRET } from '@/lib/server/env'
import { mintInternalToken } from '@/lib/server/token'
import type { Me } from '@/lib/types'

export const WORKSPACE_COOKIE = 'legora_ws'

async function requireUserId(): Promise<string> {
  const session = await auth()
  if (!session?.user?.id) redirect('/login')
  return session.user.id
}

async function send<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: {
      'content-type': 'application/json',
      authorization: `Bearer ${token}`,
      ...init?.headers,
    },
    cache: 'no-store',
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

/** Call the API as the signed-in user with no workspace context. */
export async function userApi<T>(path: string, init?: RequestInit): Promise<T> {
  const userId = await requireUserId()
  return send<T>(path, await mintInternalToken(userId), init)
}

/**
 * Who am I and which workspace am I in. Memoised per request.
 *
 * The active workspace is a cookie; if it is missing or names a workspace the
 * user is no longer in, fall back to their first membership. Server components
 * cannot set cookies, so the fallback is applied per render and made sticky by
 * the switcher action.
 */
export const resolveContext = cache(async () => {
  const userId = await requireUserId()
  const me = await send<Me>('/me', await mintInternalToken(userId))
  const jar = await cookies()
  const requested = jar.get(WORKSPACE_COOKIE)?.value
  const active = me.workspaces.find((w) => w.id === requested) ?? me.workspaces[0] ?? null
  return { me, active }
})

/** Call the API inside the active workspace. Redirects to onboarding if there is none. */
export async function workspaceApi<T>(path: string, init?: RequestInit): Promise<T> {
  const { me, active } = await resolveContext()
  if (!active) redirect('/workspaces/new')
  return send<T>(path, await mintInternalToken(me.id, active.id), init)
}

/** Pre-session call: register. Gated by the internal secret, not a token. */
export async function internalApi<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(apiUrl(path), {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-internal-secret': INTERNAL_API_SECRET },
    body: JSON.stringify(body),
    cache: 'no-store',
  })
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { detail?: unknown }
    throw new ApiError(
      typeof payload.detail === 'string' ? payload.detail : 'request failed',
      response.status,
    )
  }
  return (await response.json()) as T
}
