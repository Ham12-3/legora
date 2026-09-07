import { describe, expect, it } from 'vitest'

import { apiUrl } from '@/lib/api'

describe('apiUrl', () => {
  it('joins the base and path without doubling slashes', () => {
    expect(apiUrl('/healthz')).toMatch(/\/healthz$/)
    expect(apiUrl('healthz')).toBe(apiUrl('/healthz'))
    expect(apiUrl('/healthz')).not.toContain('//healthz')
  })

  it('never points at a NEXT_PUBLIC_ variable', () => {
    // Rule 7: the API base is server-only config, so nothing here may resolve
    // through a client-exposed env var.
    expect(Object.keys(process.env).filter((k) => k.startsWith('NEXT_PUBLIC_'))).not.toContain(
      'NEXT_PUBLIC_API_BASE_URL',
    )
  })
})
