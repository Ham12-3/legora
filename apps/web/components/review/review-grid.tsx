'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
import Link from 'next/link'
import { useEffect, useMemo, useRef, useState } from 'react'

import { AddColumnForm } from '@/components/review/add-column-form'
import { CellView } from '@/components/review/cell-view'
import { CitationPanel } from '@/components/review/citation-panel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  cellKey,
  deleteColumn,
  exportUrl,
  fetchReview,
  removeRow,
  reviewKey,
  runReview,
  streamUrl,
  upsertCell,
} from '@/lib/review-api'
import type { Cell, ReviewDetail, RunRequest } from '@/lib/types'
import { cn } from '@/lib/utils'

const ROW_HEIGHT = 64
const DOC_COL_WIDTH = 260
const COL_WIDTH = 240

type Selection = { documentId: string; columnId: string } | null

export function ReviewGrid({ reviewId, initial }: { reviewId: string; initial: ReviewDetail }) {
  const queryClient = useQueryClient()
  const [selection, setSelection] = useState<Selection>(null)
  const [adding, setAdding] = useState(false)
  const [live, setLive] = useState(false)

  const { data } = useQuery({
    queryKey: reviewKey(reviewId),
    queryFn: () => fetchReview(reviewId),
    initialData: initial,
    // SSE is the primary channel; poll slowly as a fallback while work is in flight.
    refetchInterval: (q) =>
      q.state.data?.cells.some((c) => c.status === 'pending' || c.status === 'running')
        ? 8_000
        : false,
  })

  // Live cell updates.
  useEffect(() => {
    const source = new EventSource(streamUrl(reviewId))
    source.addEventListener('ready', () => setLive(true))
    source.addEventListener('cell', (event) => {
      const cell = JSON.parse((event as MessageEvent<string>).data) as Cell
      queryClient.setQueryData<ReviewDetail>(reviewKey(reviewId), (old) =>
        old ? upsertCell(old, cell) : old,
      )
    })
    source.onerror = () => setLive(false)
    return () => source.close()
  }, [reviewId, queryClient])

  const cells = useMemo(() => {
    const map = new Map<string, Cell>()
    for (const c of data.cells) map.set(cellKey(c.document_id, c.column_id), c)
    return map
  }, [data.cells])

  const invalidate = () => queryClient.invalidateQueries({ queryKey: reviewKey(reviewId) })

  const run = useMutation({
    mutationFn: (body: RunRequest) => runReview(reviewId, body),
    onSuccess: invalidate,
  })
  const dropColumn = useMutation({
    mutationFn: (columnId: string) => deleteColumn(reviewId, columnId),
    onSuccess: invalidate,
  })
  const dropRow = useMutation({
    mutationFn: (documentId: string) => removeRow(reviewId, documentId),
    onSuccess: invalidate,
  })

  const scrollRef = useRef<HTMLDivElement>(null)
  const rowVirtualizer = useVirtualizer({
    count: data.documents.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 8,
    // Same first render on server and client, so hydration does not diverge
    // before the scroll element has been measured.
    initialRect: { width: 1200, height: 800 },
  })

  const latestRun = data.runs[0]
  const inFlight = data.cells.filter((c) => c.status === 'pending' || c.status === 'running').length
  const unverified = data.cells.filter(
    (c) => c.status === 'done' && !c.verified && !c.not_found,
  ).length
  const selectedColumn = selection ? data.columns.find((c) => c.id === selection.columnId) : null
  const selectedDocument = selection
    ? data.documents.find((d) => d.document_id === selection.documentId)
    : null
  const gridWidth = DOC_COL_WIDTH + data.columns.length * COL_WIDTH

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col gap-4">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link
            href={`/matters/${data.review.matter_id}`}
            className="text-sm text-[var(--muted)] hover:underline"
          >
            ← Matter
          </Link>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">{data.review.name}</h1>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-[var(--muted)]">
            <span>
              {data.documents.length} documents × {data.columns.length} columns
            </span>
            {latestRun && (
              <Badge tone={latestRun.status === 'done' ? 'success' : 'info'}>
                last run: {latestRun.mode} · {latestRun.done_cells}/{latestRun.total_cells} ·{' '}
                {latestRun.status}
              </Badge>
            )}
            {inFlight > 0 && <Badge tone="info">{inFlight} in flight</Badge>}
            {unverified > 0 && <Badge tone="warning">{unverified} unverified</Badge>}
            <span title={live ? 'Live updates connected' : 'Live updates disconnected; polling'}>
              {live ? '● live' : '○ polling'}
            </span>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setAdding((v) => !v)}>
            + Column
          </Button>
          <Button
            size="sm"
            disabled={run.isPending || data.columns.length === 0 || data.documents.length === 0}
            onClick={() => run.mutate({ mode: 'auto', force: false })}
            title="Run every cell that is not already answered (cached answers are reused)"
          >
            Run all
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={run.isPending || data.columns.length === 0}
            onClick={() => {
              if (confirm('Recompute every cell, ignoring cached answers?')) {
                run.mutate({ mode: 'auto', force: true })
              }
            }}
          >
            Force rerun
          </Button>
          <a href={exportUrl(reviewId, 'csv')} className="text-sm underline underline-offset-4">
            CSV
          </a>
          <a href={exportUrl(reviewId, 'xlsx')} className="text-sm underline underline-offset-4">
            XLSX
          </a>
        </div>
      </header>

      {data.demo_mode && (
        <div className="rounded-md border border-amber-400 bg-amber-50 px-4 py-2 text-sm text-amber-900 dark:bg-amber-900/30 dark:text-amber-100">
          <strong>Demo mode.</strong> These answers were produced by a placeholder model (no
          OPENAI_API_KEY is configured). They exercise the pipeline but are not real extractions.
        </div>
      )}

      {adding && (
        <div className="max-w-md rounded-lg border border-[var(--border)] p-4">
          <AddColumnForm reviewId={reviewId} onDone={() => setAdding(false)} />
        </div>
      )}

      <div
        className={cn('flex min-h-0 flex-1 gap-0', selection && 'lg:grid lg:grid-cols-[1fr_420px]')}
      >
        <div
          ref={scrollRef}
          className="min-h-0 flex-1 overflow-auto rounded-lg border border-[var(--border)]"
        >
          <div style={{ width: gridWidth, minWidth: '100%' }}>
            {/* header */}
            <div
              className="sticky top-0 z-10 flex border-b border-[var(--border)] bg-slate-50 text-xs uppercase tracking-wide text-[var(--muted)] dark:bg-slate-900"
              style={{ height: 44 }}
            >
              <div
                className="sticky left-0 z-20 flex items-center border-r border-[var(--border)] bg-slate-50 px-3 font-medium dark:bg-slate-900"
                style={{ width: DOC_COL_WIDTH, minWidth: DOC_COL_WIDTH }}
              >
                Document
              </div>
              {data.columns.map((column) => (
                <div
                  key={column.id}
                  className="group flex items-center justify-between gap-2 border-r border-[var(--border)] px-3"
                  style={{ width: COL_WIDTH, minWidth: COL_WIDTH }}
                  title={column.question}
                >
                  <span className="truncate normal-case font-medium text-[var(--foreground)]">
                    {column.name}
                  </span>
                  <span className="flex shrink-0 gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                    <button
                      type="button"
                      className="rounded px-1 hover:bg-slate-200 dark:hover:bg-slate-800"
                      title="Rerun this column"
                      onClick={() =>
                        run.mutate({ column_id: column.id, mode: 'auto', force: true })
                      }
                    >
                      ↻
                    </button>
                    <button
                      type="button"
                      className="rounded px-1 hover:bg-slate-200 dark:hover:bg-slate-800"
                      title="Delete this column"
                      onClick={() => {
                        if (confirm(`Delete column "${column.name}" and its answers?`)) {
                          dropColumn.mutate(column.id)
                        }
                      }}
                    >
                      ✕
                    </button>
                  </span>
                </div>
              ))}
              {data.columns.length === 0 && (
                <div className="flex items-center px-3 normal-case">
                  No columns yet — add a question to start.
                </div>
              )}
            </div>

            {/* rows */}
            <div style={{ height: rowVirtualizer.getTotalSize(), position: 'relative' }}>
              {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                const doc = data.documents[virtualRow.index]
                if (!doc) return null
                return (
                  <div
                    key={doc.document_id}
                    className="group/row absolute left-0 flex w-full border-b border-[var(--border)]"
                    style={{ top: virtualRow.start, height: virtualRow.size }}
                  >
                    <div
                      className="sticky left-0 z-10 flex items-center justify-between gap-2 border-r border-[var(--border)] bg-[var(--background)] px-3 text-sm"
                      style={{ width: DOC_COL_WIDTH, minWidth: DOC_COL_WIDTH }}
                    >
                      <span className="min-w-0">
                        <span className="block truncate font-medium" title={doc.filename}>
                          {doc.filename}
                        </span>
                        <span className="text-xs text-[var(--muted)]">
                          {doc.status !== 'ready'
                            ? `document ${doc.status}`
                            : `${doc.page_count ?? '?'} pages`}
                        </span>
                      </span>
                      <span className="flex shrink-0 gap-1 opacity-0 transition-opacity group-hover/row:opacity-100">
                        <button
                          type="button"
                          className="rounded px-1 text-xs hover:bg-slate-200 dark:hover:bg-slate-800"
                          title="Rerun this row"
                          onClick={() =>
                            run.mutate({ document_id: doc.document_id, mode: 'auto', force: true })
                          }
                        >
                          ↻
                        </button>
                        <button
                          type="button"
                          className="rounded px-1 text-xs hover:bg-slate-200 dark:hover:bg-slate-800"
                          title="Remove from review"
                          onClick={() => {
                            if (confirm(`Remove "${doc.filename}" from this review?`)) {
                              dropRow.mutate(doc.document_id)
                            }
                          }}
                        >
                          ✕
                        </button>
                      </span>
                    </div>
                    {data.columns.map((column) => {
                      const cell = cells.get(cellKey(doc.document_id, column.id))
                      const isSelected =
                        selection?.documentId === doc.document_id &&
                        selection?.columnId === column.id
                      return (
                        <button
                          key={column.id}
                          type="button"
                          className="border-r border-[var(--border)] text-left hover:bg-slate-50 focus-visible:outline-none dark:hover:bg-slate-900"
                          style={{ width: COL_WIDTH, minWidth: COL_WIDTH }}
                          onClick={() =>
                            setSelection({ documentId: doc.document_id, columnId: column.id })
                          }
                        >
                          <CellView cell={cell} selected={isSelected} />
                        </button>
                      )
                    })}
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        {selection && selectedColumn && selectedDocument && (
          <CitationPanel
            cell={cells.get(cellKey(selection.documentId, selection.columnId))}
            column={selectedColumn}
            document={selectedDocument}
            onClose={() => setSelection(null)}
            onRerun={() =>
              run.mutate({
                document_id: selection.documentId,
                column_id: selection.columnId,
                mode: 'interactive',
                force: true,
              })
            }
          />
        )}
      </div>
    </div>
  )
}
