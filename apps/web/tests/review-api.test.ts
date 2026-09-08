import { describe, expect, it } from 'vitest'

import { upsertCell } from '@/lib/review-api'
import type { Cell, ReviewDetail } from '@/lib/types'

function cell(documentId: string, columnId: string, patch: Partial<Cell> = {}): Cell {
  return {
    id: `${documentId}-${columnId}`,
    review_id: 'r',
    document_id: documentId,
    column_id: columnId,
    status: 'done',
    value_text: 'x',
    value_json: 'x',
    not_found: false,
    verified: true,
    confidence: 'high',
    model: 'openai',
    prompt_version: 'v1',
    from_cache: false,
    error: null,
    updated_at: '2026-01-01T00:00:00Z',
    citations: [],
    ...patch,
  }
}

const base: ReviewDetail = {
  review: {
    id: 'r',
    matter_id: 'm',
    name: 'R',
    created_at: '2026-01-01T00:00:00Z',
    document_count: 1,
    column_count: 1,
  },
  documents: [],
  columns: [],
  cells: [cell('d1', 'c1')],
  runs: [],
  demo_mode: false,
}

describe('upsertCell', () => {
  it('replaces a cell at the same position', () => {
    const next = upsertCell(base, cell('d1', 'c1', { value_text: 'y', status: 'running' }))
    expect(next.cells).toHaveLength(1)
    expect(next.cells[0]?.value_text).toBe('y')
    expect(next.cells[0]?.status).toBe('running')
  })

  it('appends a cell for a new position', () => {
    const next = upsertCell(base, cell('d2', 'c1'))
    expect(next.cells).toHaveLength(2)
  })

  it('flips demo_mode on when a fake-model cell arrives and never back off', () => {
    const on = upsertCell(base, cell('d1', 'c1', { model: 'fake' }))
    expect(on.demo_mode).toBe(true)
    const still = upsertCell(on, cell('d1', 'c1', { model: 'openai' }))
    expect(still.demo_mode).toBe(true)
  })
})
