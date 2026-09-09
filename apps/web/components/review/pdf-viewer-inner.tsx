'use client'

import { useEffect, useLayoutEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'

export type Highlight = {
  page: number
  /** Word boxes in PDF points, origin top-left, as stored on the citation. */
  boxes: number[][]
}

type Props = {
  url: string
  page: number
  highlight: Highlight | null
  onPageChange: (page: number) => void
}

// The slice of pdf.js we use. pdf.js is loaded as a native ES module from
// public/ (see scripts/copy-pdf-worker.mjs): its build is itself a webpack
// bundle and breaks when re-bundled by Next in dev.
type PdfViewport = { width: number; height: number }
type PdfRenderTask = { promise: Promise<void>; cancel: () => void }
type PdfPage = {
  getViewport: (opts: { scale: number }) => PdfViewport
  render: (opts: {
    canvasContext: CanvasRenderingContext2D
    viewport: PdfViewport
  }) => PdfRenderTask
}
type PdfDocument = {
  numPages: number
  getPage: (n: number) => Promise<PdfPage>
}
// Cleanup goes through the loading task, which also terminates the worker.
type PdfLoadingTask = { promise: Promise<PdfDocument>; destroy: () => Promise<void> }
type PdfJs = {
  GlobalWorkerOptions: { workerSrc: string }
  getDocument: (src: { url: string }) => PdfLoadingTask
}

const PDFJS_URL = '/pdf.min.mjs'
let pdfjsPromise: Promise<PdfJs> | null = null

function loadPdfJs(): Promise<PdfJs> {
  if (!pdfjsPromise) {
    // A variable specifier plus webpackIgnore keeps webpack's hands off it.
    pdfjsPromise = (import(/* webpackIgnore: true */ PDFJS_URL) as Promise<PdfJs>).then((mod) => {
      mod.GlobalWorkerOptions.workerSrc = '/pdf.worker.min.mjs'
      return mod
    })
  }
  return pdfjsPromise
}

function describe(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

/**
 * One page at a time, sized to its container, with citation word boxes drawn
 * as an overlay. PyMuPDF and pdf.js both put the origin at the top-left in
 * points, so a box maps to CSS with a single scale factor.
 */
export default function PdfViewerInner({ url, page, highlight, onPageChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [width, setWidth] = useState(600)
  const [doc, setDoc] = useState<PdfDocument | null>(null)
  const [pageSize, setPageSize] = useState<{ w: number; h: number } | null>(null)
  const [error, setError] = useState<string | null>(null)

  useLayoutEffect(() => {
    const el = containerRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.max(240, Math.floor(entry.contentRect.width)))
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  // Load the document.
  useEffect(() => {
    let cancelled = false
    let task: PdfLoadingTask | null = null
    setError(null)
    setDoc(null)
    loadPdfJs()
      .then((pdfjs) => {
        if (cancelled) return null
        task = pdfjs.getDocument({ url })
        return task.promise
      })
      .then((d) => {
        if (d && !cancelled) setDoc(d)
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(`Could not load PDF: ${describe(e)}`)
      })
    return () => {
      cancelled = true
      void task?.destroy()
    }
  }, [url])

  // Render the current page whenever the page, width, or document changes.
  useEffect(() => {
    if (!doc) return
    const canvas = canvasRef.current
    if (!canvas) return
    let cancelled = false
    let task: PdfRenderTask | null = null
    doc
      .getPage(Math.min(Math.max(1, page), doc.numPages))
      .then((p: PdfPage) => {
        if (cancelled) return
        const base = p.getViewport({ scale: 1 })
        setPageSize({ w: base.width, h: base.height })
        const scale = width / base.width
        const viewport = p.getViewport({ scale: scale * (window.devicePixelRatio || 1) })
        canvas.width = Math.floor(viewport.width)
        canvas.height = Math.floor(viewport.height)
        canvas.style.width = `${width}px`
        canvas.style.height = `${Math.floor(base.height * scale)}px`
        const context = canvas.getContext('2d')
        if (!context) return
        task = p.render({ canvasContext: context, viewport })
        return task.promise
      })
      .catch((e: unknown) => {
        if (!cancelled && !(e instanceof Error && e.name === 'RenderingCancelledException')) {
          setError(`Could not render page: ${describe(e)}`)
        }
      })
    return () => {
      cancelled = true
      task?.cancel()
    }
  }, [doc, page, width])

  const scale = pageSize ? width / pageSize.w : 1
  const boxes = highlight && highlight.page === page ? highlight.boxes : []
  const pageCount = doc?.numPages ?? null

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between text-xs text-[var(--muted)]">
        <Button
          variant="outline"
          size="sm"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          ← Prev
        </Button>
        <span>
          Page {page}
          {pageCount ? ` of ${pageCount}` : ''}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={pageCount !== null && page >= pageCount}
          onClick={() => onPageChange(page + 1)}
        >
          Next →
        </Button>
      </div>

      <div
        ref={containerRef}
        className="relative overflow-hidden rounded-md border border-[var(--border)] bg-white"
        style={{ minHeight: pageSize ? pageSize.h * scale : 200 }}
      >
        {error ? (
          <div className="p-6 text-sm text-red-600">{error}</div>
        ) : (
          <>
            {!doc && <div className="p-6 text-sm text-[var(--muted)]">Loading page…</div>}
            <canvas ref={canvasRef} className="block" />
          </>
        )}
        {pageSize && boxes.length > 0 && (
          <div className="pointer-events-none absolute inset-0" aria-hidden>
            {boxes.map(([x0, y0, x1, y1], i) => (
              <div
                key={i}
                className="absolute rounded-sm bg-yellow-300/50 ring-1 ring-yellow-500/70"
                style={{
                  left: (x0 ?? 0) * scale,
                  top: (y0 ?? 0) * scale,
                  width: ((x1 ?? 0) - (x0 ?? 0)) * scale,
                  height: ((y1 ?? 0) - (y0 ?? 0)) * scale,
                }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
