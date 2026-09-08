'use server'

import { redirect } from 'next/navigation'

import { workspaceApi } from '@/lib/server/api'
import type { PlaybookDetail } from '@/lib/types'

export type NewPlaybookState = { error?: string }

export async function createPlaybookAction(
  _: NewPlaybookState,
  form: FormData,
): Promise<NewPlaybookState> {
  const name = String(form.get('name') ?? '').trim()
  const description = String(form.get('description') ?? '').trim()
  if (!name) return { error: 'Name is required.' }

  let detail: PlaybookDetail
  try {
    detail = await workspaceApi<PlaybookDetail>('/playbooks', {
      method: 'POST',
      body: JSON.stringify({ name, description: description || null, rules: [] }),
    })
  } catch (error) {
    return { error: error instanceof Error ? error.message : 'Could not create playbook.' }
  }
  redirect(`/playbooks/${detail.playbook.id}`)
}
