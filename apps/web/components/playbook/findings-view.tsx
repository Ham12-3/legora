'use client'

import { useQuery } from '@tanstack/react-query'
import Link from 'next/link'
import { useState } from 'react'

import type { SelectedSource } from '@/components/assistant/chat-thread'
import { SourcePanel } from '@/components/assistant/source-panel'
import { Badge } from '@/components/ui/badge'
import { clientApi } from '@/lib/client-api'
import type { Finding, PlaybookRunDetail } from '@/lib/types'
import { cn } from '@/lib/utils'

const SEVERITY_TONE = {
  none: 'success',
  low: 'warning',
  medium: 'warning',
  high: 'danger',
} as const
const POSITION_LABEL = {
  preferred: 'Preferred',
  fallback: 'Fallback',
  unacceptable: 'Unacceptable',
  not_addressed: 'Not addressed',
} as const
const ORDER = { high: 0, medium: 1, low: 2, none: 3 } as const

export function FindingsView({ runId, initial }: { runId: string; initial: PlaybookRunDetail }) {
  const [source, setSource] = useState<SelectedSource | null>(null)
  const { data } = useQuery({
    queryKey: ['playbook-run', runId],
    queryFn: () => clientApi<PlaybookRunDetail>(`/playbook-runs/${runId}`),
    initialData: initial,
    refetchInterval: (q) =>
      q.state.data && ['queued', 'running'].includes(q.state.data.run.status) ? 3_000 : false,
  })

  const findings = [...data.findings].sort(
    (a, b) => ORDER[a.severity] - ORDER[b.severity] || a.ordinal - b.ordinal,
  )
  const deviations = findings.filter((f) => f.matched_position !== 'preferred').length

  function open(f: Finding) {
    if (!f.quoted_text || f.page === null || f.char_start === null || f.char_end === null) return
    setSource({
      mimeType: data.document_mime_type,
      citation: {
        marker: f.ordinal + 1,
        document_id: f.document_id,
        filename: data.document_filename,
        chunk_id: f.chunk_id,
        quoted_text: f.quoted_text,
        page: f.page,
        char_start: f.char_start,
        char_end: f.char_end,
        bboxes: f.bboxes,
        match_kind: f.match_kind ?? 'exact',
      },
    })
  }

  return (
    <div
      className={cn(
        'h-[calc(100vh-7rem)]',
        source ? 'grid gap-0 lg:grid-cols-[1fr_440px]' : 'flex flex-col',
      )}
    >
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-2">
        <header className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <Link
              href={`/playbooks/${data.run.playbook_id}`}
              className="text-sm text-[var(--muted)] hover:underline"
            >
              ← {data.playbook_name}
            </Link>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight">{data.document_filename}</h1>
            <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-[var(--muted)]">
              <Badge
                tone={
                  data.run.status === 'done'
                    ? 'success'
                    : data.run.status === 'failed'
                      ? 'danger'
                      : 'info'
                }
              >
                {data.run.status}
              </Badge>
              {data.run.status === 'done' && (
                <span>
                  {findings.length} topics · {deviations} deviate from the preferred position
                </span>
              )}
              {data.run.error && <span className="text-red-600">{data.run.error}</span>}
            </p>
          </div>
          {data.run.status === 'done' && (
            <a
              href={`/api/proxy/playbook-runs/${runId}/export`}
              className="text-sm underline underline-offset-4"
            >
              Export issues list (DOCX)
            </a>
          )}
        </header>

        {data.demo_mode && (
          <div className="rounded-md border border-amber-400 bg-amber-50 px-4 py-2 text-sm text-amber-900 dark:bg-amber-900/30 dark:text-amber-100">
            <strong>Demo mode.</strong> Findings come from a placeholder model (no OPENAI_API_KEY).
          </div>
        )}

        {['queued', 'running'].includes(data.run.status) && (
          <p className="text-sm text-[var(--muted)]">
            Reviewing the document against the playbook…
          </p>
        )}

        <ol className="flex flex-col gap-3">
          {findings.map((f) => {
            const unverified = !f.verified && f.matched_position !== 'not_addressed'
            return (
              <li
                key={f.id}
                className={cn(
                  'rounded-lg border p-4 text-sm',
                  unverified
                    ? 'border-amber-500 border-l-4 bg-amber-50/60 dark:bg-amber-900/20'
                    : 'border-[var(--border)]',
                )}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-semibold">{f.topic}</h3>
                  <Badge tone={SEVERITY_TONE[f.severity]}>{f.severity}</Badge>
                  <Badge tone="neutral">{POSITION_LABEL[f.matched_position]}</Badge>
                  {f.clause_reference && (
                    <span className="text-xs text-[var(--muted)]">{f.clause_reference}</span>
                  )}
                  {unverified && (
                    <Badge tone="warning">⚠ Unverified — no quote matched the source</Badge>
                  )}
                </div>
                <p className="mt-2">{f.rationale}</p>
                {f.quoted_text && (
                  <button
                    type="button"
                    onClick={() => open(f)}
                    className="mt-2 block w-full rounded-md border border-[var(--border)] px-3 py-2 text-left hover:bg-slate-50 dark:hover:bg-slate-900"
                    title="Open in the document"
                  >
                    <span className="block whitespace-pre-wrap italic">“{f.quoted_text}”</span>
                    <span className="mt-1 block text-xs text-[var(--muted)]">
                      Page {f.page} · click to view
                    </span>
                  </button>
                )}
                {f.suggested_language && (
                  <div className="mt-3 rounded-md bg-slate-50 px-3 py-2 dark:bg-slate-900">
                    <p className="text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
                      Proposed language
                    </p>
                    <p className="mt-1 whitespace-pre-wrap">{f.suggested_language}</p>
                  </div>
                )}
              </li>
            )
          })}
        </ol>
      </div>

      {source && <SourcePanel source={source} onClose={() => setSource(null)} />}
    </div>
  )
}
