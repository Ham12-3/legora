import { notFound } from 'next/navigation'

import { ChatThread } from '@/components/assistant/chat-thread'
import { ApiError } from '@/lib/api'
import { workspaceApi } from '@/lib/server/api'
import type { ThreadDetail } from '@/lib/types'

type Props = { params: Promise<{ threadId: string }> }

export default async function ThreadPage({ params }: Props) {
  const { threadId } = await params
  let detail: ThreadDetail
  try {
    detail = await workspaceApi<ThreadDetail>(`/threads/${threadId}`)
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound()
    throw error
  }
  return <ChatThread threadId={threadId} initial={detail} />
}
