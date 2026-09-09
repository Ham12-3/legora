import { Badge } from '@/components/ui/badge'
import type { DocumentStatus } from '@/lib/types'

const LABELS: Record<
  DocumentStatus,
  { label: string; tone: 'neutral' | 'info' | 'success' | 'danger' }
> = {
  uploaded: { label: 'Queued', tone: 'neutral' },
  parsing: { label: 'Parsing', tone: 'info' },
  chunking: { label: 'Chunking', tone: 'info' },
  embedding: { label: 'Embedding', tone: 'info' },
  ready: { label: 'Ready', tone: 'success' },
  failed: { label: 'Failed', tone: 'danger' },
}

export const IN_PROGRESS: ReadonlySet<DocumentStatus> = new Set([
  'uploaded',
  'parsing',
  'chunking',
  'embedding',
])

export function StatusBadge({ status, isOcr }: { status: DocumentStatus; isOcr?: boolean }) {
  const { label, tone } = LABELS[status]
  return (
    <span className="inline-flex items-center gap-1.5">
      <Badge tone={tone}>{label}</Badge>
      {isOcr && <Badge tone="warning">OCR</Badge>}
    </span>
  )
}
