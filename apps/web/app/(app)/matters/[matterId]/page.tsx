import Link from 'next/link'
import { notFound } from 'next/navigation'

import { DocumentsPanel } from '@/components/documents/documents-panel'
import { NewReviewForm } from '@/components/review/new-review-form'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ApiError } from '@/lib/api'
import { formatDate } from '@/lib/format'
import { workspaceApi } from '@/lib/server/api'
import type { Document, Matter, Review } from '@/lib/types'

type Props = { params: Promise<{ matterId: string }> }

export default async function MatterPage({ params }: Props) {
  const { matterId } = await params

  let matter: Matter
  let documents: Document[]
  let reviews: Review[]
  try {
    ;[matter, documents, reviews] = await Promise.all([
      workspaceApi<Matter>(`/matters/${matterId}`),
      workspaceApi<Document[]>(`/matters/${matterId}/documents`),
      workspaceApi<Review[]>(`/reviews?matter_id=${matterId}`),
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

      <section className="grid gap-8 lg:grid-cols-[1fr_320px]">
        <div>
          <h2 className="text-lg font-semibold">
            Reviews{' '}
            <span className="text-sm font-normal text-[var(--muted)]">({reviews.length})</span>
          </h2>
          {reviews.length === 0 ? (
            <p className="mt-4 text-sm text-[var(--muted)]">
              No reviews yet. A review is a grid: documents as rows, your questions as columns.
            </p>
          ) : (
            <ul className="mt-4 divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
              {reviews.map((r) => (
                <li key={r.id}>
                  <Link
                    href={`/reviews/${r.id}`}
                    className="flex items-center justify-between px-4 py-3 text-sm hover:bg-slate-50 dark:hover:bg-slate-900"
                  >
                    <span className="font-medium">{r.name}</span>
                    <span className="text-xs text-[var(--muted)]">
                      {r.document_count} docs × {r.column_count} cols · {formatDate(r.created_at)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
        <aside>
          <Card>
            <CardHeader>
              <CardTitle>New review</CardTitle>
              <CardDescription>
                Only documents that finished ingestion can be reviewed.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <NewReviewForm matterId={matter.id} documents={documents} />
            </CardContent>
          </Card>
        </aside>
      </section>

      <DocumentsPanel matterId={matter.id} initialDocuments={documents} />
    </div>
  )
}
