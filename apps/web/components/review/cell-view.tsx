'use client'

import type { Cell } from '@/lib/types'
import { cn } from '@/lib/utils'

const CONFIDENCE: Record<string, string> = {
  high: 'bg-emerald-500',
  medium: 'bg-amber-500',
  low: 'bg-red-500',
}

/**
 * One grid square. Rule 2 in CLAUDE.md: an unverified answer must never look
 * like a verified one, so unverified cells get an amber bar and a label, not
 * just a different icon.
 */
export function CellView({ cell, selected }: { cell: Cell | undefined; selected: boolean }) {
  const base = cn(
    'flex h-full min-h-14 w-full flex-col justify-center gap-1 px-3 py-2 text-left text-sm',
    selected && 'ring-2 ring-inset ring-slate-500',
  )

  if (!cell) {
    return <div className={cn(base, 'text-[var(--muted)]')}>—</div>
  }

  if (cell.status === 'pending' || cell.status === 'running') {
    return (
      <div className={cn(base, 'text-[var(--muted)]')}>
        <span className="inline-flex items-center gap-2">
          <span
            aria-hidden
            className={cn(
              'inline-block size-3 rounded-full border-2 border-slate-300 border-t-slate-600',
              cell.status === 'running' && 'animate-spin',
            )}
          />
          {cell.status === 'running' ? 'Running…' : 'Queued'}
        </span>
      </div>
    )
  }

  if (cell.status === 'failed') {
    return (
      <div className={cn(base, 'text-red-600 dark:text-red-400')} title={cell.error ?? undefined}>
        Failed
        {cell.error && <span className="line-clamp-2 text-xs opacity-80">{cell.error}</span>}
      </div>
    )
  }

  if (cell.not_found) {
    return <div className={cn(base, 'italic text-[var(--muted)]')}>Not found</div>
  }

  const citations = cell.citations ?? []
  const meta = [
    cell.confidence && `confidence: ${cell.confidence}`,
    cell.model && `model: ${cell.model}`,
    cell.from_cache && 'served from cache',
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <div
      className={cn(
        base,
        !cell.verified && 'border-l-4 border-amber-500 bg-amber-50/60 dark:bg-amber-900/20',
      )}
      title={meta}
    >
      <span className="line-clamp-3 break-words">{cell.value_text}</span>
      <span className="flex items-center gap-2 text-xs text-[var(--muted)]">
        {cell.confidence && (
          <span
            aria-label={`confidence ${cell.confidence}`}
            className={cn('inline-block size-1.5 rounded-full', CONFIDENCE[cell.confidence])}
          />
        )}
        {cell.verified ? (
          <span>
            {citations.length} {citations.length === 1 ? 'citation' : 'citations'}
          </span>
        ) : (
          <span className="font-medium text-amber-700 dark:text-amber-300">
            ⚠ Unverified — no quote matched the source
          </span>
        )}
      </span>
    </div>
  )
}
