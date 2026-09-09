'use server'

import { revalidatePath } from 'next/cache'
import { redirect } from 'next/navigation'

import { workspaceApi } from '@/lib/server/api'
import type { Matter } from '@/lib/types'

export type NewMatterState = { error?: string }

export async function createMatterAction(
  _: NewMatterState,
  form: FormData,
): Promise<NewMatterState> {
  const name = String(form.get('name') ?? '').trim()
  const description = String(form.get('description') ?? '').trim()
  if (!name) return { error: 'Name is required.' }

  let matter: Matter
  try {
    matter = await workspaceApi<Matter>('/matters', {
      method: 'POST',
      body: JSON.stringify({ name, description: description || null }),
    })
  } catch (error) {
    return { error: error instanceof Error ? error.message : 'Could not create matter.' }
  }

  revalidatePath('/matters')
  redirect(`/matters/${matter.id}`)
}

export async function deleteMatterAction(matterId: string): Promise<void> {
  await workspaceApi<void>(`/matters/${matterId}`, { method: 'DELETE' })
  revalidatePath('/matters')
  redirect('/matters')
}
