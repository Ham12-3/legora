/**
 * Browser upload pipeline: hash -> presign -> PUT to object storage -> register.
 *
 * Pure helpers here are unit-tested; the DOM-bound pieces (XHR for progress,
 * WebCrypto for hashing) are injected so the orchestration can be tested with
 * fakes.
 */

import { ApiError } from '@/lib/api'
import type { Document, PresignResponse } from '@/lib/types'

export const MAX_FILES_PER_BATCH = 200
export const UPLOAD_CONCURRENCY = 4

export const ACCEPTED_MIME_TYPES: Record<string, string> = {
  'application/pdf': '.pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
}

export type UploadStage =
  'queued' | 'hashing' | 'presigning' | 'uploading' | 'registering' | 'done' | 'duplicate' | 'error'

export type UploadItem = {
  id: string
  file: File
  stage: UploadStage
  /** 0..1, upload bytes only */
  progress: number
  error?: string
  document?: Document
}

export function toHex(bytes: ArrayBuffer): string {
  return Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, '0')).join('')
}

export async function sha256Hex(file: Blob): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
  return toHex(digest)
}

/** Infer a MIME type when the browser leaves `file.type` blank (common for .docx on Windows). */
export function resolveMimeType(file: File): string | null {
  if (file.type && file.type in ACCEPTED_MIME_TYPES) return file.type
  const lower = file.name.toLowerCase()
  if (lower.endsWith('.pdf')) return 'application/pdf'
  if (lower.endsWith('.docx')) {
    return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
  }
  return null
}

/**
 * Run `fn` over `items` with at most `limit` in flight. Resolves when every
 * item has settled; per-item failures are the caller's business.
 */
export async function runWithConcurrency<T>(
  items: readonly T[],
  limit: number,
  fn: (item: T, index: number) => Promise<void>,
): Promise<void> {
  let next = 0
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length) {
      const index = next++
      const item = items[index]
      if (item === undefined) continue
      await fn(item, index)
    }
  })
  await Promise.all(workers)
}

export type UploadDeps = {
  presign: (matterId: string, body: PresignBody) => Promise<PresignResponse>
  put: (
    url: string,
    file: File,
    mimeType: string,
    onProgress: (ratio: number) => void,
  ) => Promise<void>
  register: (matterId: string, body: RegisterBody) => Promise<Document>
  hash?: (file: Blob) => Promise<string>
}

export type PresignBody = {
  filename: string
  mime_type: string
  size_bytes: number
  sha256: string
}

export type RegisterBody = PresignBody & { document_id: string; storage_key: string }

export type StageReporter = (patch: Partial<UploadItem>) => void

export async function uploadOne(
  matterId: string,
  file: File,
  report: StageReporter,
  deps: UploadDeps,
): Promise<void> {
  const mimeType = resolveMimeType(file)
  if (!mimeType) {
    report({ stage: 'error', error: 'Only PDF and DOCX files are supported' })
    return
  }

  try {
    report({ stage: 'hashing' })
    const sha256 = await (deps.hash ?? sha256Hex)(file)

    report({ stage: 'presigning' })
    const base: PresignBody = {
      filename: file.name,
      mime_type: mimeType,
      size_bytes: file.size,
      sha256,
    }
    const ticket = await deps.presign(matterId, base)

    if (ticket.duplicate) {
      report({ stage: 'duplicate', document: ticket.document ?? undefined, progress: 1 })
      return
    }
    if (!ticket.upload_url || !ticket.document_id || !ticket.storage_key) {
      throw new Error('Malformed upload ticket')
    }

    report({ stage: 'uploading', progress: 0 })
    await deps.put(ticket.upload_url, file, mimeType, (ratio) => report({ progress: ratio }))

    report({ stage: 'registering', progress: 1 })
    let document: Document
    try {
      document = await deps.register(matterId, {
        ...base,
        document_id: ticket.document_id,
        storage_key: ticket.storage_key,
      })
    } catch (error) {
      // Two identical files in one batch both pass the presign check; the
      // unique constraint decides, and the loser is a duplicate, not a failure.
      if (error instanceof ApiError && error.status === 409) {
        report({ stage: 'duplicate' })
        return
      }
      throw error
    }
    report({ stage: 'done', document })
  } catch (error) {
    report({ stage: 'error', error: error instanceof Error ? error.message : 'Upload failed' })
  }
}

/** PUT with progress events. fetch() cannot report upload progress, so XHR it is. */
export function xhrPut(
  url: string,
  file: File,
  mimeType: string,
  onProgress: (ratio: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', url)
    // Must match the ContentType the API signed, or the signature fails.
    xhr.setRequestHeader('Content-Type', mimeType)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total)
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve()
      else reject(new Error(`Storage rejected the upload (${xhr.status})`))
    }
    xhr.onerror = () => reject(new Error('Network error while uploading'))
    xhr.send(file)
  })
}
