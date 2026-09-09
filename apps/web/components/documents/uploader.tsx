'use client'

import { useCallback, useRef, useState, type DragEvent } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { clientApi } from '@/lib/client-api'
import { formatBytes } from '@/lib/format'
import type { Document, PresignResponse } from '@/lib/types'
import {
  ACCEPTED_MIME_TYPES,
  MAX_FILES_PER_BATCH,
  UPLOAD_CONCURRENCY,
  runWithConcurrency,
  uploadOne,
  xhrPut,
  type PresignBody,
  type RegisterBody,
  type UploadItem,
} from '@/lib/upload'
import { cn } from '@/lib/utils'

const deps = {
  presign: (matterId: string, body: PresignBody) =>
    clientApi<PresignResponse>(`/matters/${matterId}/documents/presign`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  put: xhrPut,
  register: (matterId: string, body: RegisterBody) =>
    clientApi<Document>(`/matters/${matterId}/documents`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}

const ACCEPT = Object.values(ACCEPTED_MIME_TYPES).join(',')

export function Uploader({ matterId, onSettled }: { matterId: string; onSettled: () => void }) {
  const [items, setItems] = useState<UploadItem[]>([])
  const [dragging, setDragging] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const patch = useCallback((id: string, update: Partial<UploadItem>) => {
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, ...update } : it)))
  }, [])

  const enqueue = useCallback(
    async (files: File[]) => {
      if (files.length === 0) return
      setNotice(
        files.length > MAX_FILES_PER_BATCH
          ? `Only the first ${MAX_FILES_PER_BATCH} files were queued.`
          : null,
      )
      const batch = files.slice(0, MAX_FILES_PER_BATCH).map<UploadItem>((file) => ({
        id: crypto.randomUUID(),
        file,
        stage: 'queued',
        progress: 0,
      }))
      setItems((prev) => [...batch, ...prev])

      await runWithConcurrency(batch, UPLOAD_CONCURRENCY, async (item) => {
        await uploadOne(matterId, item.file, (update) => patch(item.id, update), deps)
        onSettled()
      })
    },
    [matterId, onSettled, patch],
  )

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setDragging(false)
    void enqueue(Array.from(event.dataTransfer.files))
  }

  const active = items.filter((i) => !['done', 'duplicate', 'error'].includes(i.stage))
  const finished = items.length - active.length

  return (
    <Card>
      <CardHeader>
        <CardTitle>Upload documents</CardTitle>
        <CardDescription>
          PDF or DOCX, up to {MAX_FILES_PER_BATCH} at a time. Files go straight to storage;
          duplicates within this matter are skipped.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div
          role="button"
          tabIndex={0}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn(
            'flex cursor-pointer flex-col items-center justify-center rounded-md border border-dashed px-4 py-8 text-center text-sm transition-colors',
            dragging
              ? 'border-slate-500 bg-slate-50 dark:bg-slate-900'
              : 'border-[var(--border)] hover:bg-slate-50 dark:hover:bg-slate-900',
          )}
        >
          <p className="font-medium">Drop files here</p>
          <p className="mt-1 text-xs text-[var(--muted)]">or click to choose</p>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ACCEPT}
            className="hidden"
            onChange={(e) => {
              void enqueue(Array.from(e.target.files ?? []))
              e.target.value = ''
            }}
          />
        </div>

        {notice && <p className="text-xs text-amber-700 dark:text-amber-300">{notice}</p>}

        {items.length > 0 && (
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between text-xs text-[var(--muted)]">
              <span>
                {active.length > 0
                  ? `${active.length} in progress · ${finished} finished`
                  : `${finished} finished`}
              </span>
              {active.length === 0 && (
                <Button variant="ghost" size="sm" onClick={() => setItems([])}>
                  Clear
                </Button>
              )}
            </div>
            <ul className="flex max-h-80 flex-col gap-2 overflow-y-auto">
              {items.map((item) => (
                <UploadRow key={item.id} item={item} />
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

const STAGE_LABEL: Record<UploadItem['stage'], string> = {
  queued: 'Queued',
  hashing: 'Hashing',
  presigning: 'Preparing',
  uploading: 'Uploading',
  registering: 'Registering',
  done: 'Uploaded',
  duplicate: 'Already in matter',
  error: 'Failed',
}

function UploadRow({ item }: { item: UploadItem }) {
  const pct = Math.round(item.progress * 100)
  const tone =
    item.stage === 'done'
      ? 'success'
      : item.stage === 'error'
        ? 'danger'
        : item.stage === 'duplicate'
          ? 'warning'
          : 'info'

  return (
    <li className="rounded-md border border-[var(--border)] px-3 py-2 text-xs">
      <div className="flex items-center justify-between gap-2">
        <span className="min-w-0 truncate font-medium" title={item.file.name}>
          {item.file.name}
        </span>
        <Badge tone={tone}>{STAGE_LABEL[item.stage]}</Badge>
      </div>
      <div className="mt-1 flex items-center justify-between text-[var(--muted)]">
        <span>{formatBytes(item.file.size)}</span>
        {item.stage === 'uploading' && <span className="tabular-nums">{pct}%</span>}
      </div>
      {item.stage === 'uploading' && (
        <div className="mt-1.5 h-1 overflow-hidden rounded bg-slate-200 dark:bg-slate-800">
          <div className="h-full bg-slate-900 dark:bg-slate-100" style={{ width: `${pct}%` }} />
        </div>
      )}
      {item.error && <p className="mt-1 text-red-600 dark:text-red-400">{item.error}</p>}
    </li>
  )
}
