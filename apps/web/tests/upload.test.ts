import { describe, expect, it } from 'vitest'

import { ApiError } from '@/lib/api'

import {
  resolveMimeType,
  runWithConcurrency,
  sha256Hex,
  toHex,
  uploadOne,
  type UploadDeps,
  type UploadItem,
} from '@/lib/upload'
import type { Document } from '@/lib/types'

const DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

describe('runWithConcurrency', () => {
  it('never exceeds the limit and processes every item', async () => {
    let inFlight = 0
    let peak = 0
    const seen: number[] = []
    await runWithConcurrency([1, 2, 3, 4, 5, 6, 7], 3, async (n) => {
      inFlight++
      peak = Math.max(peak, inFlight)
      await new Promise((r) => setTimeout(r, 2))
      seen.push(n)
      inFlight--
    })
    expect(peak).toBeLessThanOrEqual(3)
    expect(seen.sort()).toEqual([1, 2, 3, 4, 5, 6, 7])
  })

  it('handles an empty list', async () => {
    await expect(runWithConcurrency([], 4, async () => {})).resolves.toBeUndefined()
  })
})

describe('hashing', () => {
  it('produces lowercase 64-char hex the API accepts', async () => {
    const digest = await sha256Hex(new Blob(['hello']))
    expect(digest).toBe('2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824')
    expect(toHex(new Uint8Array([0, 15, 255]).buffer)).toBe('000fff')
  })
})

describe('resolveMimeType', () => {
  it('falls back to the extension when the browser gives no type', () => {
    expect(resolveMimeType(new File([''], 'a.docx', { type: '' }))).toBe(DOCX)
    expect(resolveMimeType(new File([''], 'a.PDF', { type: '' }))).toBe('application/pdf')
    expect(resolveMimeType(new File([''], 'a.exe', { type: '' }))).toBeNull()
  })
})

function deps(overrides: Partial<UploadDeps> = {}): UploadDeps & { calls: string[] } {
  const calls: string[] = []
  const doc = { id: 'd1', status: 'uploaded' } as unknown as Document
  return {
    calls,
    hash: async () => 'a'.repeat(64),
    presign: async () => {
      calls.push('presign')
      return {
        duplicate: false,
        document_id: 'd1',
        storage_key: 'k',
        upload_url: 'http://s3/put',
        expires_in: 900,
        document: null,
      }
    },
    put: async (_url, _file, _mime, onProgress) => {
      calls.push('put')
      onProgress(0.5)
      onProgress(1)
    },
    register: async () => {
      calls.push('register')
      return doc
    },
    ...overrides,
  }
}

function recorder() {
  const stages: string[] = []
  let progress = 0
  const report = (patch: Partial<UploadItem>) => {
    if (patch.stage) stages.push(patch.stage)
    if (patch.progress !== undefined) progress = patch.progress
  }
  return { stages, report, progress: () => progress }
}

describe('uploadOne', () => {
  it('walks hash -> presign -> put -> register -> done', async () => {
    const d = deps()
    const r = recorder()
    await uploadOne('m1', new File(['x'], 'a.pdf', { type: 'application/pdf' }), r.report, d)
    expect(r.stages).toEqual(['hashing', 'presigning', 'uploading', 'registering', 'done'])
    expect(d.calls).toEqual(['presign', 'put', 'register'])
    expect(r.progress()).toBe(1)
  })

  it('skips the upload entirely when the API reports a duplicate', async () => {
    const existing = { id: 'old' } as unknown as Document
    const d = deps({
      presign: async () => ({
        duplicate: true,
        document: existing,
        document_id: null,
        storage_key: null,
        upload_url: null,
        expires_in: null,
      }),
    })
    const r = recorder()
    await uploadOne('m1', new File(['x'], 'a.pdf', { type: 'application/pdf' }), r.report, d)
    expect(r.stages).toEqual(['hashing', 'presigning', 'duplicate'])
    // The overridden presign does not record itself; what matters is that
    // nothing was PUT or registered.
    expect(d.calls).toEqual([])
  })

  it('treats a 409 from register as a duplicate that lost the race', async () => {
    const d = deps({
      register: async () => {
        throw new ApiError('already exists', 409)
      },
    })
    const r = recorder()
    await uploadOne('m1', new File(['x'], 'a.pdf', { type: 'application/pdf' }), r.report, d)
    expect(r.stages.at(-1)).toBe('duplicate')
    expect(d.calls).toEqual(['presign', 'put'])
  })

  it('rejects unsupported types before touching the network', async () => {
    const d = deps()
    const r = recorder()
    await uploadOne('m1', new File(['x'], 'a.exe', { type: '' }), r.report, d)
    expect(r.stages).toEqual(['error'])
    expect(d.calls).toEqual([])
  })

  it('surfaces a storage failure as an error stage, not a throw', async () => {
    const d = deps({
      put: async () => {
        throw new Error('Storage rejected the upload (403)')
      },
    })
    const r = recorder()
    await uploadOne('m1', new File(['x'], 'a.pdf', { type: 'application/pdf' }), r.report, d)
    expect(r.stages.at(-1)).toBe('error')
    expect(d.calls).toEqual(['presign'])
  })
})
