'use client'

import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import type { SelectedSource } from '@/components/assistant/chat-thread'
import { PdfViewer, type Highlight } from '@/components/review/pdf-viewer'
import { Button } from '@/components/ui/button'
import { clientApi } from '@/lib/client-api'
import type { DownloadOut } from '@/lib/types'

const MATCH_LABEL: Record<string, string> = {
  exact: 'Exact match',
  relocated: 'Exact match (passage relabelled)',
  fuzzy: 'Close match — source text shown',
}

/** The cited passage, and for PDFs the page with the words highlighted. */
export function SourcePanel({ source, onClose }: { source: SelectedSource; onClose: () => void }) {
  const { citation, mimeType } = source
  const isPdf = mimeType === 'application/pdf'
  const [page, setPage] = useState(citation.page)
  useEffect(() => setPage(citation.page), [citation])

  const download = useQuery({
    queryKey: ['download', citation.document_id],
    queryFn: () => clientApi<DownloadOut>(`/documents/${citation.document_id}/download`),
    enabled: isPdf,
    staleTime: 10 * 60 * 1000,
  })

  const highlight: Highlight = {
    page: citation.page,
    boxes: Object.entries(citation.bboxes)
      .filter(([p]) => Number(p) === page)
      .flatMap(([, boxes]) => boxes as number[][]),
  }

  return (
    <aside className="flex h-full flex-col gap-4 overflow-y-auto border-l border-[var(--border)] bg-[var(--background)] p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-xs text-[var(--muted)]" title={citation.filename}>
            {citation.filename}
          </p>
          <h3 className="font-semibold">Source [{citation.marker}]</h3>
        </div>
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close panel">
          ✕
        </Button>
      </div>
      <blockquote className="rounded-md border border-[var(--border)] px-3 py-2 text-sm">
        <span className="block whitespace-pre-wrap">“{citation.quoted_text}”</span>
        <span className="mt-1 block text-xs text-[var(--muted)]">
          Page {citation.page} · {MATCH_LABEL[citation.match_kind] ?? citation.match_kind}
        </span>
      </blockquote>
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
