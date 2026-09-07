'use server'

import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

import { WORKSPACE_COOKIE, userApi } from '@/lib/server/api'
import type { Workspace } from '@/lib/types'

export type NewWorkspaceState = { error?: string }

export async function createWorkspaceAction(
  _: NewWorkspaceState,
  form: FormData,
): Promise<NewWorkspaceState> {
  const name = String(form.get('name') ?? '').trim()
  if (!name) return { error: 'Name is required.' }

  let workspace: Workspace
  try {
    workspace = await userApi<Workspace>('/workspaces', {
      method: 'POST',
      body: JSON.stringify({ name }),
    })
  } catch (error) {
    return { error: error instanceof Error ? error.message : 'Could not create workspace.' }
  }

  const jar = await cookies()
  jar.set(WORKSPACE_COOKIE, workspace.id, {
    httpOnly: true,
    sameSite: 'lax',
    path: '/',
    maxAge: 60 * 60 * 24 * 365,
  })
  redirect('/matters')
}
