import Link from 'next/link'
import { notFound } from 'next/navigation'

import { LocalTime } from '@/components/local-time'
import { DocumentsPanel } from '@/components/documents/documents-panel'
import { NewThreadForm } from '@/components/assistant/new-thread-form'
import { NewReviewForm } from '@/components/review/new-review-form'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ApiError } from '@/lib/api'
import { workspaceApi } from '@/lib/server/api'
import type { Document, Matter, Review, Thread } from '@/lib/types'

type Props = { params: Promise<{ matterId: string }> }

export default async function MatterPage({ params }: Props) {
  const { matterId } = await params

  let matter: Matter
  let documents: Document[]
  let reviews: Review[]
  let threads: Thread[]
  try {
    ;[matter, documents, reviews, threads] = await Promise.all([
      workspaceApi<Matter>(`/matters/${matterId}`),
      workspaceApi<Document[]>(`/matters/${matterId}/documents`),
      workspaceApi<Review[]>(`/reviews?matter_id=${matterId}`),
      workspaceApi<Thread[]>(`/threads?matter_id=${matterId}`),
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
          <LocalTime iso={matter.created_at} />
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
                      {r.document_count} docs × {r.column_count} cols ·{' '}
                      <LocalTime iso={r.created_at} />
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

      <section className="grid gap-8 lg:grid-cols-[1fr_320px]">
        <div>
          <h2 className="text-lg font-semibold">
            Assistant{' '}
            <span className="text-sm font-normal text-[var(--muted)]">({threads.length})</span>
          </h2>
          {threads.length === 0 ? (
            <p className="mt-4 text-sm text-[var(--muted)]">
              No conversations yet. Ask questions across a set of documents; every answer is cited,
              and the assistant says so when the documents are silent.
            </p>
          ) : (
            <ul className="mt-4 divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
              {threads.map((t) => (
                <li key={t.id}>
                  <Link
                    href={`/threads/${t.id}`}
                    className="flex items-center justify-between px-4 py-3 text-sm hover:bg-slate-50 dark:hover:bg-slate-900"
                  >
                    <span className="truncate font-medium">{t.title}</span>
                    <span className="shrink-0 text-xs text-[var(--muted)]">
                      {t.document_count} docs · {t.message_count} messages ·{' '}
                      <LocalTime iso={t.created_at} />
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
              <CardTitle>Ask the documents</CardTitle>
              <CardDescription>Grounded chat over the documents you pick.</CardDescription>
            </CardHeader>
            <CardContent>
              <NewThreadForm matterId={matter.id} documents={documents} />
            </CardContent>
          </Card>
        </aside>
      </section>

      <DocumentsPanel matterId={matter.id} initialDocuments={documents} />
    </div>
  )
}
