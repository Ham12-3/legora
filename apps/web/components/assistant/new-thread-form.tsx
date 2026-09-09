'use client'

import { useActionState } from 'react'

import { createThreadAction, type NewThreadState } from '@/app/(app)/matters/[matterId]/actions'
import { FormMessage } from '@/components/form-message'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import type { Document } from '@/lib/types'

const initial: NewThreadState = {}

export function NewThreadForm({
  matterId,
  documents,
}: {
  matterId: string
  documents: Document[]
}) {
  const bound = createThreadAction.bind(null, matterId)
  const [state, action, pending] = useActionState(bound, initial)
  const ready = documents.filter((d) => d.status === 'ready')

  return (
    <form action={action} className="flex flex-col gap-4">
      <fieldset className="flex flex-col gap-1.5">
        <legend className="mb-1 text-sm font-medium">
          <Label>Documents to ask about</Label>
        </legend>
        {ready.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">No documents are ready yet.</p>
        ) : (
          <div className="max-h-40 overflow-y-auto rounded-md border border-[var(--border)] p-2">
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
      <Button type="submit" variant="outline" disabled={pending || ready.length === 0}>
        {pending ? 'Opening…' : 'New conversation'}
      </Button>
    </form>
  )
}
