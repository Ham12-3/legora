'use client'

import { useEffect, useState } from 'react'

import { formatDate } from '@/lib/format'

/**
 * A timestamp in the reader's own timezone.
 *
 * `Intl.DateTimeFormat` formats in whatever zone the environment is in. The
 * server runs in UTC and the browser does not, so calling it directly inside a
 * client component is a guaranteed hydration mismatch: the server writes
 * 17:40, the client renders 18:40, and React regenerates the tree.
 *
 * The server's rendering is kept for the first paint, so the cell is never
 * empty and the column never jumps; `suppressHydrationWarning` covers the
 * frame where the two disagree, and the effect settles it on the reader's
 * zone. The machine-readable value stays on the `datetime` attribute.
 */
export function LocalTime({ iso }: { iso: string }) {
  const [text, setText] = useState(() => formatDate(iso))

  useEffect(() => {
    setText(formatDate(iso))
  }, [iso])

  return (
    <time dateTime={iso} suppressHydrationWarning>
      {text}
    </time>
  )
}
