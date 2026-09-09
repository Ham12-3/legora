/** Browser-side calls for the review grid. Everything goes through the proxy. */

import { clientApi } from '@/lib/client-api'
import type {
  Cell,
  ColumnCreate,
  ReviewColumn,
  ReviewDetail,
  ReviewRun,
  RunRequest,
} from '@/lib/types'

export const reviewKey = (reviewId: string) => ['review', reviewId] as const

export function fetchReview(reviewId: string): Promise<ReviewDetail> {
  return clientApi<ReviewDetail>(`/reviews/${reviewId}`)
}

export function runReview(reviewId: string, body: RunRequest): Promise<ReviewRun> {
  return clientApi<ReviewRun>(`/reviews/${reviewId}/run`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function addColumn(reviewId: string, body: ColumnCreate): Promise<ReviewColumn> {
  return clientApi<ReviewColumn>(`/reviews/${reviewId}/columns`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function deleteColumn(reviewId: string, columnId: string): Promise<void> {
  return clientApi<void>(`/reviews/${reviewId}/columns/${columnId}`, { method: 'DELETE' })
}

export function removeRow(reviewId: string, documentId: string): Promise<void> {
  return clientApi<void>(`/reviews/${reviewId}/documents/${documentId}`, { method: 'DELETE' })
}

export function exportUrl(reviewId: string, format: 'csv' | 'xlsx'): string {
  return `/api/proxy/reviews/${reviewId}/export?format=${format}`
}

export function streamUrl(reviewId: string): string {
  return `/api/proxy/reviews/${reviewId}/stream`
}

/** Merge one cell event into a cached ReviewDetail. */
export function upsertCell(detail: ReviewDetail, cell: Cell): ReviewDetail {
  const index = detail.cells.findIndex(
    (c) => c.document_id === cell.document_id && c.column_id === cell.column_id,
  )
  const cells = index === -1 ? [...detail.cells, cell] : detail.cells.with(index, cell)
  return {
    ...detail,
    cells,
    demo_mode: detail.demo_mode || cell.model === 'fake',
  }
}

export function cellKey(documentId: string, columnId: string): string {
  return `${documentId}:${columnId}`
}
