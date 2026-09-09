'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState, type FormEvent } from 'react'

import { FormMessage } from '@/components/form-message'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { clientApi } from '@/lib/client-api'
import type { Document, Matter, PlaybookDetail, PlaybookRule, PlaybookRun } from '@/lib/types'

const playbookKey = (id: string) => ['playbook', id] as const

export function PlaybookEditor({
  playbookId,
  initial,
  matters,
}: {
  playbookId: string
  initial: PlaybookDetail
  matters: Matter[]
}) {
  const queryClient = useQueryClient()
  const router = useRouter()
  const [error, setError] = useState<string | null>(null)
  const [matterId, setMatterId] = useState(matters[0]?.id ?? '')
  const [documentId, setDocumentId] = useState('')

  const { data } = useQuery({
    queryKey: playbookKey(playbookId),
    queryFn: () => clientApi<PlaybookDetail>(`/playbooks/${playbookId}`),
    initialData: initial,
  })
  const invalidate = () => queryClient.invalidateQueries({ queryKey: playbookKey(playbookId) })

  const addRule = useMutation({
    mutationFn: (form: FormData) =>
      clientApi<PlaybookRule>(`/playbooks/${playbookId}/rules`, {
        method: 'POST',
        body: JSON.stringify({
          topic: String(form.get('topic') ?? '').trim(),
          preferred_position: String(form.get('preferred') ?? '').trim(),
          fallback_position: String(form.get('fallback') ?? '').trim() || null,
          unacceptable_position: String(form.get('unacceptable') ?? '').trim() || null,
        }),
      }),
    onSuccess: invalidate,
    onError: (e) => setError(e instanceof Error ? e.message : 'Could not add rule'),
  })
  const removeRule = useMutation({
    mutationFn: (ruleId: string) =>
      clientApi<void>(`/playbooks/${playbookId}/rules/${ruleId}`, { method: 'DELETE' }),
    onSuccess: invalidate,
  })

  const documents = useQuery({
    queryKey: ['documents', matterId],
    queryFn: () => clientApi<Document[]>(`/matters/${matterId}/documents`),
    enabled: !!matterId,
  })
  const ready = (documents.data ?? []).filter((d) => d.status === 'ready')

  const run = useMutation({
    mutationFn: () =>
      clientApi<PlaybookRun>(`/playbooks/${playbookId}/run`, {
        method: 'POST',
        body: JSON.stringify({ document_id: documentId }),
      }),
    onSuccess: (r) => router.push(`/playbook-runs/${r.id}`),
    onError: (e) => setError(e instanceof Error ? e.message : 'Could not start the run'),
  })

  function onAddRule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    const form = new FormData(event.currentTarget)
    addRule.mutate(form)
    event.currentTarget.reset()
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_360px]">
      <section>
        <Link href="/playbooks" className="text-sm text-[var(--muted)] hover:underline">
          ← Playbooks
        </Link>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">{data.playbook.name}</h1>
        {data.playbook.description && (
          <p className="mt-1 text-sm text-[var(--muted)]">{data.playbook.description}</p>
        )}

        <h2 className="mt-8 text-lg font-semibold">
          Rules{' '}
          <span className="text-sm font-normal text-[var(--muted)]">({data.rules.length})</span>
        </h2>
        {data.rules.length === 0 ? (
          <p className="mt-3 text-sm text-[var(--muted)]">
            No rules yet. Each rule is a topic with your preferred, fallback, and unacceptable
            positions.
          </p>
        ) : (
          <ol className="mt-3 flex flex-col gap-3">
            {data.rules.map((r) => (
              <li key={r.id} className="rounded-lg border border-[var(--border)] p-4 text-sm">
                <div className="flex items-start justify-between gap-3">
                  <h3 className="font-semibold">{r.topic}</h3>
                  <Button variant="ghost" size="sm" onClick={() => removeRule.mutate(r.id)}>
                    Delete
                  </Button>
                </div>
                <dl className="mt-2 grid gap-1.5">
                  <div className="flex gap-2">
                    <dt className="w-28 shrink-0">
                      <Badge tone="success">Preferred</Badge>
                    </dt>
                    <dd>{r.preferred_position}</dd>
                  </div>
                  {r.fallback_position && (
                    <div className="flex gap-2">
                      <dt className="w-28 shrink-0">
                        <Badge tone="warning">Fallback</Badge>
                      </dt>
                      <dd>{r.fallback_position}</dd>
                    </div>
                  )}
                  {r.unacceptable_position && (
                    <div className="flex gap-2">
                      <dt className="w-28 shrink-0">
                        <Badge tone="danger">Unacceptable</Badge>
                      </dt>
                      <dd>{r.unacceptable_position}</dd>
                    </div>
                  )}
                </dl>
              </li>
            ))}
          </ol>
        )}

        <form
          onSubmit={onAddRule}
          className="mt-6 flex flex-col gap-3 rounded-lg border border-[var(--border)] p-4"
        >
          <h3 className="font-semibold">Add a rule</h3>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rule-topic">Topic</Label>
            <Input id="rule-topic" name="topic" placeholder="Limitation of liability" required />
          </div>
          {(['preferred', 'fallback', 'unacceptable'] as const).map((field) => (
            <div key={field} className="flex flex-col gap-1.5">
              <Label htmlFor={`rule-${field}`} className="capitalize">
                {field} position{field === 'preferred' ? '' : ' (optional)'}
              </Label>
              <textarea
                id={`rule-${field}`}
                name={field}
                rows={2}
                required={field === 'preferred'}
                className="rounded-md border border-[var(--border)] bg-transparent px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
              />
            </div>
          ))}
          <FormMessage error={error} />
          <Button type="submit" disabled={addRule.isPending} className="self-start">
            {addRule.isPending ? 'Adding…' : 'Add rule'}
          </Button>
        </form>
      </section>

      <aside>
        <Card>
          <CardHeader>
            <CardTitle>Run against a document</CardTitle>
            <CardDescription>One finding per rule, each cited to the clause.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="run-matter">Matter</Label>
              <select
                id="run-matter"
                value={matterId}
                onChange={(e) => {
                  setMatterId(e.target.value)
                  setDocumentId('')
                }}
                className="h-9 rounded-md border border-[var(--border)] bg-transparent px-2 text-sm"
              >
                {matters.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="run-document">Document</Label>
              <select
                id="run-document"
                value={documentId}
                onChange={(e) => setDocumentId(e.target.value)}
                className="h-9 rounded-md border border-[var(--border)] bg-transparent px-2 text-sm"
              >
                <option value="">
                  {documents.isLoading
                    ? 'Loading…'
                    : ready.length
                      ? 'Choose…'
                      : 'No ready documents'}
                </option>
                {ready.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.filename}
                  </option>
                ))}
              </select>
            </div>
            <Button
              disabled={!documentId || data.rules.length === 0 || run.isPending}
              onClick={() => run.mutate()}
            >
              {run.isPending ? 'Starting…' : 'Run playbook'}
            </Button>
            {data.rules.length === 0 && (
              <p className="text-xs text-[var(--muted)]">Add at least one rule first.</p>
            )}
          </CardContent>
        </Card>
      </aside>
    </div>
  )
}
