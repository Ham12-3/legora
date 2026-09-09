'use client'

import { useQuery, useQueryClient } from '@tanstack/react-query'
import Link from 'next/link'
import { useEffect, useRef, useState, type FormEvent } from 'react'

import { MessageBubble } from '@/components/assistant/message-bubble'
import { SourcePanel } from '@/components/assistant/source-panel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { clientApi } from '@/lib/client-api'
import { readSse } from '@/lib/sse'
import type { Message, MessageCitation, ThreadDetail } from '@/lib/types'

const threadKey = (id: string) => ['thread', id] as const

type Draft = { text: string; stage: 'retrieving' | 'generating' | null }

export type SelectedSource = { citation: MessageCitation; mimeType: string }

export function ChatThread({ threadId, initial }: { threadId: string; initial: ThreadDetail }) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [source, setSource] = useState<SelectedSource | null>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const { data } = useQuery({
    queryKey: threadKey(threadId),
    queryFn: () => clientApi<ThreadDetail>(`/threads/${threadId}`),
    initialData: initial,
  })

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [data.messages.length, draft?.text])

  function appendMessage(message: Message) {
    queryClient.setQueryData<ThreadDetail>(threadKey(threadId), (old) =>
      old
        ? {
            ...old,
            messages: old.messages.some((m) => m.id === message.id)
              ? old.messages.map((m) => (m.id === message.id ? message : m))
              : [...old.messages, message],
            demo_mode: old.demo_mode || message.model === 'fake',
          }
        : old,
    )
  }

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const content = inputRef.current?.value.trim()
    if (!content || draft) return
    if (inputRef.current) inputRef.current.value = ''
    setError(null)
    setDraft({ text: '', stage: 'retrieving' })

    try {
      const response = await fetch(`/api/proxy/threads/${threadId}/messages`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ content }),
      })
      if (!response.ok) throw new Error(`Request failed (${response.status})`)
      for await (const { event: kind, data: payload } of readSse(response)) {
        if (kind === 'status') {
          const stage = (payload as { stage: Draft['stage'] }).stage
          setDraft((d) => ({ text: d?.text ?? '', stage }))
        } else if (kind === 'delta') {
          const text = (payload as { text: string }).text
          setDraft((d) => ({ text: (d?.text ?? '') + text, stage: 'generating' }))
        } else if (kind === 'message') {
          appendMessage(payload as Message)
        } else if (kind === 'error') {
          setError((payload as { detail: string }).detail)
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong')
    } finally {
      setDraft(null)
      await queryClient.invalidateQueries({ queryKey: threadKey(threadId) })
    }
  }

  const documentsById = new Map(data.documents.map((d) => [d.document_id, d]))

  return (
    <div
      className={
        source
          ? 'grid h-[calc(100vh-7rem)] gap-0 lg:grid-cols-[1fr_440px]'
          : 'flex h-[calc(100vh-7rem)] flex-col'
      }
    >
      <div className="flex min-h-0 flex-1 flex-col">
        <header className="mb-3 flex flex-wrap items-start justify-between gap-3">
          <div>
            <Link
              href={`/matters/${data.thread.matter_id}`}
              className="text-sm text-[var(--muted)] hover:underline"
            >
              ← Matter
            </Link>
            <h1 className="mt-1 text-xl font-semibold tracking-tight">{data.thread.title}</h1>
            <p className="mt-1 flex flex-wrap gap-1 text-xs text-[var(--muted)]">
              {data.documents.map((d) => (
                <Badge key={d.document_id} tone={d.status === 'ready' ? 'neutral' : 'warning'}>
                  {d.filename}
                  {d.status !== 'ready' ? ` (${d.status})` : ''}
                </Badge>
              ))}
            </p>
          </div>
        </header>

        {data.demo_mode && (
          <div className="mb-3 rounded-md border border-amber-400 bg-amber-50 px-4 py-2 text-sm text-amber-900 dark:bg-amber-900/30 dark:text-amber-100">
            <strong>Demo mode.</strong> Answers come from a placeholder model (no OPENAI_API_KEY).
            The retrieval, citation checking, and refusal behaviour are real; the prose is not.
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto rounded-lg border border-[var(--border)] p-4">
          {data.messages.length === 0 && !draft && (
            <p className="text-sm text-[var(--muted)]">
              Ask a question about the selected documents. Every answer cites the exact passage it
              came from, and the assistant says so when the documents are silent.
            </p>
          )}
          <ol className="flex flex-col gap-4">
            {data.messages.map((m) => (
              <MessageBubble
                key={m.id}
                message={m}
                onCitation={(c) =>
                  setSource({
                    citation: c,
                    mimeType: documentsById.get(c.document_id)?.mime_type ?? 'application/pdf',
                  })
                }
              />
            ))}
            {draft && (
              <li className="max-w-3xl rounded-lg border border-[var(--border)] px-4 py-3 text-sm">
                {draft.text ? (
                  <p className="whitespace-pre-wrap">{draft.text}▍</p>
                ) : (
                  <p className="text-[var(--muted)]">
                    {draft.stage === 'retrieving' ? 'Searching the documents…' : 'Writing…'}
                  </p>
                )}
              </li>
            )}
          </ol>
          <div ref={bottomRef} />
        </div>

        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

        <form onSubmit={send} className="mt-3 flex items-end gap-2">
          <textarea
            ref={inputRef}
            rows={2}
            placeholder="e.g. What is the liability cap, and does it carve out fraud?"
            disabled={!!draft}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                e.currentTarget.form?.requestSubmit()
              }
            }}
            className="flex-1 resize-none rounded-md border border-[var(--border)] bg-transparent px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
          />
          <Button type="submit" disabled={!!draft}>
            {draft ? 'Answering…' : 'Ask'}
          </Button>
        </form>
      </div>

      {source && <SourcePanel source={source} onClose={() => setSource(null)} />}
    </div>
  )
}
