import Link from 'next/link'
import { notFound } from 'next/navigation'

import { DocumentsPanel } from '@/components/documents/documents-panel'
import { ApiError } from '@/lib/api'
import { formatDate } from '@/lib/format'
import { workspaceApi } from '@/lib/server/api'
import type { Document, Matter } from '@/lib/types'

type Props = { params: Promise<{ matterId: string }> }

export default async function MatterPage({ params }: Props) {
  const { matterId } = await params

  let matter: Matter
  let documents: Document[]
  try {
    ;[matter, documents] = await Promise.all([
      workspaceApi<Matter>(`/matters/${matterId}`),
      workspaceApi<Document[]>(`/matters/${matterId}/documents`),
    ])
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound()
    throw error
  }

  return (
    <div className="flex flex-col gap-8">
      <div>
        <Link href="/matters" className="text-sm text-[var(--muted)] hover:underline">
          ← Matters
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">{matter.name}</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          {matter.description ? `${matter.description} · ` : ''}Created{' '}
          {formatDate(matter.created_at)}
        </p>
      </div>

      <DocumentsPanel matterId={matter.id} initialDocuments={documents} />
    </div>
  )
}
