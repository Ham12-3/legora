'use client'

import dynamic from 'next/dynamic'

export type { Highlight } from './pdf-viewer-inner'

/** pdf.js touches `DOMMatrix` at import time; never render it on the server. */
export const PdfViewer = dynamic(() => import('./pdf-viewer-inner'), {
  ssr: false,
  loading: () => (
    <div className="flex h-64 items-center justify-center text-sm text-[var(--muted)]">
      Loading viewer…
    </div>
  ),
})
