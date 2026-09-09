import { notFound } from 'next/navigation'

import { PlaybookEditor } from '@/components/playbook/playbook-editor'
import { ApiError } from '@/lib/api'
import { workspaceApi } from '@/lib/server/api'
import type { Matter, PlaybookDetail } from '@/lib/types'

type Props = { params: Promise<{ playbookId: string }> }

export default async function PlaybookPage({ params }: Props) {
  const { playbookId } = await params
  let detail: PlaybookDetail
  let matters: Matter[]
  try {
    ;[detail, matters] = await Promise.all([
      workspaceApi<PlaybookDetail>(`/playbooks/${playbookId}`),
      workspaceApi<Matter[]>('/matters'),
    ])
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound()
    throw error
  }
  return <PlaybookEditor playbookId={playbookId} initial={detail} matters={matters} />
}
