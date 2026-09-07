'use server'

import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

import { signOut } from '@/auth'
import { WORKSPACE_COOKIE, userApi } from '@/lib/server/api'
import type { Workspace } from '@/lib/types'

export async function switchWorkspace(workspaceId: string): Promise<void> {
  // Only ever store a workspace the user is actually in.
  const workspaces = await userApi<Workspace[]>('/workspaces')
  if (!workspaces.some((w) => w.id === workspaceId)) return

  const jar = await cookies()
  jar.set(WORKSPACE_COOKIE, workspaceId, {
    httpOnly: true,
    sameSite: 'lax',
    path: '/',
    maxAge: 60 * 60 * 24 * 365,
  })
  redirect('/matters')
}

export async function signOutAction(): Promise<void> {
  const jar = await cookies()
  jar.delete(WORKSPACE_COOKIE)
  await signOut({ redirectTo: '/login' })
}
