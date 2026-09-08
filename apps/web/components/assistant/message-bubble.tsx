'use client'

import { Fragment } from 'react'

import { Badge } from '@/components/ui/badge'
import type { Message, MessageCitation } from '@/lib/types'
import { cn } from '@/lib/utils'

const MARKER = /\[(\d+)\]/g

/** Render [n] markers as clickable chips bound to their verified citation. */
function withChips(
  text: string,
  citations: MessageCitation[],
  onCitation: (c: MessageCitation) => void,
) {
  const byMarker = new Map(citations.map((c) => [c.marker, c]))
  const parts: (string | MessageCitation)[] = []
  let last = 0
  for (const match of text.matchAll(MARKER)) {
    const marker = Number(match[1])
    const citation = byMarker.get(marker)
    parts.push(text.slice(last, match.index))
    parts.push(citation ?? match[0])
    last = (match.index ?? 0) + match[0].length
  }
  parts.push(text.slice(last))
  return parts.map((part, i) =>
    typeof part === 'string' ? (
      <Fragment key={i}>{part}</Fragment>
    ) : (
      <button
        key={i}
        type="button"
        onClick={() => onCitation(part)}
        title={`${part.filename}, page ${part.page}: “${part.quoted_text.slice(0, 120)}”`}
        className="mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-slate-900 px-1.5 align-text-bottom text-[11px] font-medium text-white hover:bg-slate-700 dark:bg-slate-100 dark:text-slate-900"
      >
        {part.marker}
      </button>
    ),
  )
}

export function MessageBubble({
  message,
  onCitation,
}: {
  message: Message
  onCitation: (c: MessageCitation) => void
}) {
  const citations = message.citations ?? []
  if (message.role === 'user') {
    return (
      <li className="ml-auto max-w-2xl rounded-lg bg-slate-900 px-4 py-3 text-sm text-white dark:bg-slate-100 dark:text-slate-900">
        <p className="whitespace-pre-wrap">{message.content}</p>
      </li>
    )
  }

  const unverified = !message.verified && !message.insufficient
  return (
    <li
      className={cn(
        'max-w-3xl rounded-lg border px-4 py-3 text-sm',
        unverified
          ? 'border-amber-500 border-l-4 bg-amber-50/60 dark:bg-amber-900/20'
          : 'border-[var(--border)]',
      )}
    >
      <p className="whitespace-pre-wrap leading-relaxed">
        {withChips(message.content, citations, onCitation)}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
        {message.insufficient ? (
          <Badge tone="neutral">Not answered — the documents are silent on this</Badge>
        ) : message.verified ? (
          <Badge tone="success">
            {citations.length} verified {citations.length === 1 ? 'citation' : 'citations'}
          </Badge>
        ) : (
          <Badge tone="warning">⚠ Unverified — no quote matched the source</Badge>
        )}
        {message.error && <Badge tone="danger">{message.error}</Badge>}
        {message.model && <span className="text-[var(--muted)]">{message.model}</span>}
      </div>
    </li>
  )
}
