'use client'

import { useActionState } from 'react'

import { createReviewAction, type NewReviewState } from '@/app/(app)/matters/[matterId]/actions'
import { FormMessage } from '@/components/form-message'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { Document } from '@/lib/types'

const initial: NewReviewState = {}

export function NewReviewForm({
  matterId,
  documents,
}: {
  matterId: string
  documents: Document[]
}) {
  const bound = createReviewAction.bind(null, matterId)
  const [state, action, pending] = useActionState(bound, initial)
  const ready = documents.filter((d) => d.status === 'ready')

  return (
    <form action={action} className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Label htmlFor="review-name">Review name</Label>
        <Input id="review-name" name="name" placeholder="Supplier contracts — key terms" required />
      </div>
      <fieldset className="flex flex-col gap-1.5">
        <legend className="mb-1 text-sm font-medium">
          Documents{' '}
          <span className="text-[var(--muted)]">
            ({ready.length} ready
            {ready.length !== documents.length
              ? `, ${documents.length - ready.length} not ready`
              : ''}
            )
          </span>
        </legend>
        {ready.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">
            No documents are ready yet. Upload some and wait for ingestion.
          </p>
        ) : (
          <div className="max-h-48 overflow-y-auto rounded-md border border-[var(--border)] p-2">
            {ready.map((d) => (
              <label key={d.id} className="flex items-center gap-2 py-1 text-sm">
                <input type="checkbox" name="document_ids" value={d.id} defaultChecked />
                <span className="truncate">{d.filename}</span>
              </label>
            ))}
          </div>
        )}
      </fieldset>
      <FormMessage error={state.error} />
      <Button type="submit" disabled={pending || ready.length === 0}>
        {pending ? 'Creating…' : 'Create review'}
      </Button>
    </form>
  )
}
