import { describe, expect, it } from 'vitest'

import { workspaceLabels } from '@/lib/workspace-label'
import type { Workspace } from '@/lib/types'

function ws(id: string, name: string, role: Workspace['role']): Workspace {
  return { id, name, role, created_at: '2026-01-01T00:00:00Z' }
}

describe('workspaceLabels', () => {
  it('leaves distinct names alone', () => {
    const labels = workspaceLabels([
      ws('a', 'Hale & Partners', 'owner'),
      ws('b', 'Orion', 'member'),
    ])
    expect(labels.get('a')).toBe('Hale & Partners')
    expect(labels.get('b')).toBe('Orion')
  })

  it('separates a shared name by role', () => {
    // You register, which makes you an owner, and someone adds you to theirs.
    const labels = workspaceLabels([
      ws('mine', 'hale and healthy', 'owner'),
      ws('theirs', 'hale and healthy', 'member'),
    ])
    expect(labels.get('mine')).toBe('hale and healthy (owner)')
    expect(labels.get('theirs')).toBe('hale and healthy (member)')
  })

  it('falls back to the id when name and role both collide', () => {
    const labels = workspaceLabels([
      ws('abcd1234', 'Acme', 'member'),
      ws('efgh5678', 'Acme', 'member'),
    ])
    expect(labels.get('abcd1234')).toBe('Acme (member · abcd)')
    expect(labels.get('efgh5678')).toBe('Acme (member · efgh)')
  })

  it('only disambiguates the names that clash', () => {
    const labels = workspaceLabels([
      ws('a', 'Acme', 'owner'),
      ws('b', 'Acme', 'member'),
      ws('c', 'Orion', 'owner'),
    ])
    expect(labels.get('c')).toBe('Orion')
  })
})
