'use client'

/**
 * A scale model of the review grid for the landing page.
 *
 * The data is fictional and static — this is an illustration, not a live
 * review — but the two states that matter are the real ones: a verified answer
 * and an unverified answer wearing the amber bar it wears in the product
 * (rule 2 in CLAUDE.md). Cells fill in on a stagger the way they do over SSE.
 */

import { useEffect, useRef, useState } from 'react'

type Cell =
  | { kind: 'answer'; value: string; quote: string }
  | { kind: 'unverified'; value: string }
  | { kind: 'not-found' }

const COLUMNS = [
  'Governing law',
  'Liability cap',
  'Auto-renewal',
  'Assignment on change of control',
]

const ROWS: { document: string; cells: Cell[] }[] = [
  {
    document: 'Northwind — Master Services Agreement.pdf',
    cells: [
      {
        kind: 'answer',
        value: 'England and Wales',
        quote: 'governed by the laws of England and Wales',
      },
      { kind: 'answer', value: '125% of fees', quote: 'shall not exceed 125% of the Fees paid' },
      {
        kind: 'answer',
        value: 'Yes — 12 months',
        quote: 'renew automatically for successive periods of twelve (12) months',
      },
      { kind: 'not-found' },
    ],
  },
  {
    document: 'Orion — Reseller Agreement.pdf',
    cells: [
      { kind: 'answer', value: 'New York', quote: 'the internal laws of the State of New York' },
      {
        kind: 'answer',
        value: '£2,000,000',
        quote: 'aggregate liability shall not exceed £2,000,000',
      },
      {
        kind: 'answer',
        value: 'No',
        quote: 'expire at the end of the Initial Term unless renewed in writing',
      },
      {
        kind: 'answer',
        value: 'Consent required',
        quote: 'may not assign without the prior written consent',
      },
    ],
  },
  {
    document: 'Vertex — Data Processing Addendum.pdf',
    cells: [
      { kind: 'answer', value: 'Ireland', quote: 'the laws of Ireland' },
      { kind: 'not-found' },
      { kind: 'not-found' },
      { kind: 'unverified', value: 'Permitted to affiliates' },
    ],
  },
  {
    document: 'Halcyon — Software Licence.pdf',
    cells: [
      { kind: 'answer', value: 'Scotland', quote: 'the laws of Scotland' },
      { kind: 'answer', value: '3× annual fees', quote: 'three (3) times the annual Licence Fees' },
      {
        kind: 'answer',
        value: 'Yes — 12 months',
        quote: 'automatically renews for further twelve (12) month terms',
      },
      {
        kind: 'answer',
        value: 'Terminable',
        quote: 'may terminate on a change of Control of the Licensee',
      },
    ],
  },
]

const TOTAL = ROWS.length * COLUMNS.length

export function GridDemo() {
  const [revealed, setRevealed] = useState(0)
  const hostRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const host = hostRef.current
    if (!host) return

    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setRevealed(TOTAL)
      return
    }

    let timer: ReturnType<typeof setInterval> | undefined
    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0]
        if (!entry?.isIntersecting || timer) return
        timer = setInterval(() => {
          setRevealed((n) => {
            if (n >= TOTAL) {
              if (timer) clearInterval(timer)
              return n
            }
            return n + 1
          })
        }, 160)
      },
      { threshold: 0.35 },
    )
    observer.observe(host)

    return () => {
      observer.disconnect()
      if (timer) clearInterval(timer)
    }
  }, [])

  const running = revealed < TOTAL

  return (
    <div ref={hostRef} className="landing-panel overflow-hidden rounded-lg">
      <div className="flex items-center justify-between gap-4 border-b border-[var(--l-rule)] px-5 py-3">
        <div className="flex items-baseline gap-3">
          <span className="text-sm font-medium">Q3 vendor contracts</span>
          <span className="text-xs text-[var(--l-dim)]">4 documents, 4 questions</span>
        </div>
        <span className="text-xs tabular-nums text-[var(--l-dim)]" aria-live="polite">
          {running ? `Running ${revealed}/${TOTAL}` : `${TOTAL} of ${TOTAL} cells`}
        </span>
      </div>

      {/* border-separate, not border-collapse: a sticky cell in a collapsed
          table paints below its neighbours, and the first column bleeds. */}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[46rem] border-separate border-spacing-0 text-left">
          <thead>
            <tr>
              <th
                scope="col"
                className="sticky left-0 z-20 w-[17rem] bg-[var(--l-panel)] px-5 py-3 text-xs font-medium text-[var(--l-dim)]"
              >
                Document
              </th>
              {COLUMNS.map((column) => (
                <th
                  key={column}
                  scope="col"
                  className="border-l border-[var(--l-rule)] px-4 py-3 text-xs font-medium text-[var(--l-dim)]"
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ROWS.map((row, rowIndex) => (
              <tr key={row.document}>
                <th
                  scope="row"
                  className="sticky left-0 z-20 max-w-[17rem] truncate border-t border-[var(--l-rule)] bg-[var(--l-panel)] px-5 py-3.5 text-sm font-normal"
                  title={row.document}
                >
                  {row.document}
                </th>
                {row.cells.map((cell, columnIndex) => {
                  const index = rowIndex * COLUMNS.length + columnIndex
                  return (
                    <td
                      key={COLUMNS[columnIndex]}
                      className="border-t border-l border-[var(--l-rule)] px-4 py-3.5 align-top"
                    >
                      {index < revealed ? (
                        <CellBody cell={cell} />
                      ) : (
                        <span className="block h-3 w-2/3 animate-pulse rounded bg-[var(--l-sunk)]" />
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function CellBody({ cell }: { cell: Cell }) {
  if (cell.kind === 'not-found') {
    return <span className="landing-cell text-sm text-[var(--l-dim)] italic">Not found</span>
  }

  if (cell.kind === 'unverified') {
    return (
      <div className="landing-cell border-l-2 border-[var(--l-amber)] pl-2.5">
        <p className="text-sm">{cell.value}</p>
        <p className="mt-1 text-[11px] font-medium tracking-wide text-[var(--l-amber)] uppercase">
          Unverified
        </p>
      </div>
    )
  }

  return (
    <div className="landing-cell">
      <p className="text-sm">{cell.value}</p>
      <p className="mt-1 truncate text-[11px] text-[var(--l-dim)]">“{cell.quote}”</p>
    </div>
  )
}
