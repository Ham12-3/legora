'use server'

import { redirect } from 'next/navigation'

import { workspaceApi } from '@/lib/server/api'
import type { Review, Thread } from '@/lib/types'

export type NewReviewState = { error?: string }

export async function createReviewAction(
  matterId: string,
  _: NewReviewState,
  form: FormData,
): Promise<NewReviewState> {
  const name = String(form.get('name') ?? '').trim()
  const documentIds = form.getAll('document_ids').map(String)
  if (!name) return { error: 'Name is required.' }
  if (documentIds.length === 0) return { error: 'Pick at least one document.' }

  let review: Review
  try {
    review = await workspaceApi<Review>('/reviews', {
      method: 'POST',
      body: JSON.stringify({ matter_id: matterId, name, document_ids: documentIds }),
    })
  } catch (error) {
    return { error: error instanceof Error ? error.message : 'Could not create review.' }
  }
  redirect(`/reviews/${review.id}`)
}

export type NewThreadState = { error?: string }

export async function createThreadAction(
  matterId: string,
  _: NewThreadState,
  form: FormData,
): Promise<NewThreadState> {
  const documentIds = form.getAll('document_ids').map(String)
  if (documentIds.length === 0) return { error: 'Pick at least one document.' }

  let thread: Thread
  try {
    thread = await workspaceApi<Thread>('/threads', {
      method: 'POST',
      body: JSON.stringify({ matter_id: matterId, document_ids: documentIds }),
    })
  } catch (error) {
    return { error: error instanceof Error ? error.message : 'Could not start a conversation.' }
  }
  redirect(`/threads/${thread.id}`)
}
