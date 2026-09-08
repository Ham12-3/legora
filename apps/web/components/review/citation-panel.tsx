'use client'

import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'

import { PdfViewer, type Highlight } from '@/components/review/pdf-viewer'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { clientApi } from '@/lib/client-api'
import type { Cell, Citation, DownloadOut, ReviewColumn, ReviewDocument } from '@/lib/types'
import { cn } from '@/lib/utils'

const MATCH_LABEL: Record<string, string> = {
  exact: 'Exact match',
  relocated: 'Exact match (passage relabelled)',
  fuzzy: 'Close match — source text shown',
}

type Props = {
  cell: Cell | undefined
  column: ReviewColumn
  document: ReviewDocument
  onClose: () => void
  onRerun: () => void
}

export function CitationPanel({ cell, column, document, onClose, onRerun }: Props) {
  const [active, setActive] = useState(0)
  const [page, setPage] = useState(1)
  const citations = useMemo(() => cell?.citations ?? [], [cell?.citations])
  const current: Citation | undefined = citations[active]
  const isPdf = document.mime_type === 'application/pdf'

  useEffect(() => {
    setActive(0)
    setPage(citations[0]?.page ?? 1)
  }, [cell?.id, citations])

  const download = useQuery({
    queryKey: ['download', document.document_id],
    queryFn: () => clientApi<DownloadOut>(`/documents/${document.document_id}/download`),
    enabled: isPdf,
    staleTime: 10 * 60 * 1000,
  })

  const highlight: Highlight | null = current
    ? {
        page: current.page,
        boxes: Object.entries(current.bboxes)
          .filter(([p]) => Number(p) === page)
          .flatMap(([, boxes]) => boxes as number[][]),
      }
    : null

  return (
    <aside className="flex h-full flex-col gap-4 overflow-y-auto border-l border-[var(--border)] bg-[var(--background)] p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-xs text-[var(--muted)]" title={document.filename}>
            {document.filename}
          </p>
          <h3 className="truncate font-semibold">{column.name}</h3>
          <p className="mt-1 text-sm text-[var(--muted)]">{column.question}</p>
        </div>
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close panel">
          ✕
        </Button>
      </div>

      <div className="rounded-md border border-[var(--border)] p-3 text-sm">
        {!cell || cell.status !== 'done' ? (
          <p className="text-[var(--muted)]">
            {cell?.status === 'failed' ? `Failed: ${cell.error}` : 'No answer yet.'}
          </p>
        ) : cell.not_found ? (
          <p className="italic text-[var(--muted)]">
            Not found — the document does not address this question.
          </p>
        ) : (
          <>
            <p className="whitespace-pre-wrap">{cell.value_text}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
              {cell.verified ? (
                <Badge tone="success">Verified</Badge>
              ) : (
                <Badge tone="warning">Unverified — no quote matched the source</Badge>
              )}
              {cell.confidence && <Badge tone="neutral">confidence: {cell.confidence}</Badge>}
              {cell.model && <Badge tone="neutral">{cell.model}</Badge>}
              {cell.from_cache && <Badge tone="neutral">cached</Badge>}
            </div>
          </>
        )}
        <div className="mt-3">
          <Button variant="outline" size="sm" onClick={onRerun}>
            Rerun this cell
          </Button>
        </div>
      </div>

      {citations.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
            Citations ({citations.length})
          </p>
          <ol className="flex flex-col gap-2">
            {citations.map((c, i) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => {
                    setActive(i)
                    setPage(c.page)
                  }}
                  className={cn(
                    'w-full rounded-md border px-3 py-2 text-left text-sm',
                    i === active
                      ? 'border-slate-500 bg-slate-50 dark:bg-slate-900'
                      : 'border-[var(--border)] hover:bg-slate-50 dark:hover:bg-slate-900',
                  )}
                >
                  <span className="block whitespace-pre-wrap">“{c.quoted_text}”</span>
                  <span className="mt-1 block text-xs text-[var(--muted)]">
                    Page {c.page} · {MATCH_LABEL[c.match_kind] ?? c.match_kind}
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </div>
      )}

      {isPdf ? (
        download.data ? (
          <PdfViewer
            url={download.data.url}
            page={page}
            highlight={highlight}
            onPageChange={setPage}
          />
        ) : (
          <p className="text-sm text-[var(--muted)]">
            {download.isError ? 'Could not fetch the document.' : 'Fetching document…'}
          </p>
        )
      ) : (
        <p className="text-sm text-[var(--muted)]">
          Word documents have no page view yet; the cited text is shown above.
        </p>
      )}
    </aside>
  )
}
