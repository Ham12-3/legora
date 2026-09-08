import { notFound } from 'next/navigation'

import { FindingsView } from '@/components/playbook/findings-view'
import { ApiError } from '@/lib/api'
import { workspaceApi } from '@/lib/server/api'
import type { PlaybookRunDetail } from '@/lib/types'

type Props = { params: Promise<{ runId: string }> }

export default async function PlaybookRunPage({ params }: Props) {
  const { runId } = await params
  let detail: PlaybookRunDetail
  try {
    detail = await workspaceApi<PlaybookRunDetail>(`/playbook-runs/${runId}`)
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound()
    throw error
  }
  return <FindingsView runId={runId} initial={detail} />
}
