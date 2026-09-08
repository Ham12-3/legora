'use client'

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'

import { FormMessage } from '@/components/form-message'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { addColumn, reviewKey, runReview } from '@/lib/review-api'
import type { OutputType } from '@/lib/types'

const TYPES: { value: OutputType; label: string }[] = [
  { value: 'text', label: 'Text' },
  { value: 'boolean', label: 'Yes / No' },
  { value: 'date', label: 'Date' },
  { value: 'money', label: 'Money' },
  { value: 'enum', label: 'One of…' },
]

export function AddColumnForm({ reviewId, onDone }: { reviewId: string; onDone: () => void }) {
  const queryClient = useQueryClient()
  const [outputType, setOutputType] = useState<OutputType>('text')
  const [error, setError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: async (form: FormData) => {
      const options = String(form.get('enum_options') ?? '')
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
      const column = await addColumn(reviewId, {
        name: String(form.get('name') ?? '').trim(),
        question: String(form.get('question') ?? '').trim(),
        output_type: outputType,
        enum_options: outputType === 'enum' ? options : null,
      })
      if (form.get('run_now')) {
        await runReview(reviewId, { column_id: column.id, mode: 'auto', force: false })
      }
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: reviewKey(reviewId) })
      onDone()
    },
    onError: (e) => setError(e instanceof Error ? e.message : 'Could not add column'),
  })

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    create.mutate(new FormData(event.currentTarget))
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="col-name">Column name</Label>
        <Input id="col-name" name="name" placeholder="Governing law" required autoFocus />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="col-question">Question</Label>
        <textarea
          id="col-question"
          name="question"
          required
          rows={3}
          placeholder="Which law governs this agreement?"
          className="rounded-md border border-[var(--border)] bg-transparent px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="col-type">Answer type</Label>
        <select
          id="col-type"
          value={outputType}
          onChange={(e) => setOutputType(e.target.value as OutputType)}
          className="h-9 rounded-md border border-[var(--border)] bg-transparent px-2 text-sm"
        >
          {TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
      </div>
      {outputType === 'enum' && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="col-options">Options (comma-separated)</Label>
          <Input
            id="col-options"
            name="enum_options"
            placeholder="England and Wales, New York, Other"
            required
          />
        </div>
      )}
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" name="run_now" defaultChecked /> Run this column now
      </label>
      <FormMessage error={error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={create.isPending}>
          {create.isPending ? 'Adding…' : 'Add column'}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  )
}
