/**
 * Thin proxy for client components.
 *
 * The browser never holds an API token. Client-side fetches come here, we
 * attach the internal JWT for the signed-in user and their active workspace,
 * and forward. Only the prefixes below are reachable — /auth in particular is
 * not, so the internal secret stays internal.
 */

import { NextResponse, type NextRequest } from 'next/server'

import { auth } from '@/auth'
import { apiUrl } from '@/lib/api'
import { resolveContext } from '@/lib/server/api'
import { mintInternalToken } from '@/lib/server/token'

const ALLOWED_PREFIXES = new Set([
  'matters',
  'documents',
  'reviews',
  'threads',
  'playbooks',
  'playbook-runs',
  'workspace',
  'workspaces',
  'me',
])

type Params = { params: Promise<{ path: string[] }> }

async function forward(request: NextRequest, { params }: Params): Promise<Response> {
  const { path } = await params
  const [head] = path
  if (!head || !ALLOWED_PREFIXES.has(head)) {
    return NextResponse.json({ detail: 'not found' }, { status: 404 })
  }

  const session = await auth()
  if (!session?.user?.id) {
    return NextResponse.json({ detail: 'unauthenticated' }, { status: 401 })
  }

  const { active } = await resolveContext()
  const token = await mintInternalToken(session.user.id, active?.id)

  const target = new URL(apiUrl(`/${path.join('/')}`))
  target.search = request.nextUrl.search

  const headers = new Headers({ authorization: `Bearer ${token}` })
  const contentType = request.headers.get('content-type')
  if (contentType) headers.set('content-type', contentType)

  const hasBody = request.method !== 'GET' && request.method !== 'HEAD'
  const upstream = await fetch(target, {
    method: request.method,
    headers,
    body: hasBody ? await request.text() : undefined,
    cache: 'no-store',
  })

  const responseHeaders = new Headers({
    'content-type': upstream.headers.get('content-type') ?? 'application/json',
  })
  // Exports set a filename; SSE must not be buffered or cached.
  for (const name of ['content-disposition', 'cache-control', 'x-accel-buffering']) {
    const value = upstream.headers.get(name)
    if (value) responseHeaders.set(name, value)
  }
  return new NextResponse(upstream.body, { status: upstream.status, headers: responseHeaders })
}

export { forward as GET, forward as POST, forward as PATCH, forward as DELETE }
