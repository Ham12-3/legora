'use server'

import { revalidatePath } from 'next/cache'

import { ApiError } from '@/lib/api'
import { workspaceApi } from '@/lib/server/api'

export type AddMemberState = { error?: string; added?: string }

export async function addMemberAction(_: AddMemberState, form: FormData): Promise<AddMemberState> {
  const email = String(form.get('email') ?? '').trim()
  const role = String(form.get('role') ?? 'member')
  if (!email) return { error: 'Email is required.' }

  try {
    await workspaceApi('/workspace/members', {
      method: 'POST',
      body: JSON.stringify({ email, role }),
    })
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message }
    return { error: 'Could not add member.' }
  }

  revalidatePath('/members')
  return { added: email }
}
