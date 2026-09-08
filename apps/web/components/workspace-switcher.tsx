'use client'

import { useTransition } from 'react'

import { switchWorkspace } from '@/app/(app)/actions'
import type { Workspace } from '@/lib/types'
import { workspaceLabels } from '@/lib/workspace-label'

export function WorkspaceSwitcher({
  workspaces,
  activeId,
}: {
  workspaces: Workspace[]
  activeId: string
}) {
  const labels = workspaceLabels(workspaces)
  const [pending, start] = useTransition()

  return (
    <select
      aria-label="Workspace"
      value={activeId}
      disabled={pending}
      onChange={(e) => {
        const id = e.target.value
        if (id === '__new') {
          window.location.assign('/workspaces/new')
          return
        }
        start(() => switchWorkspace(id))
      }}
      className="h-8 rounded-md border border-[var(--border)] bg-transparent px-2 text-sm"
    >
      {workspaces.map((w) => (
        <option key={w.id} value={w.id}>
          {labels.get(w.id) ?? w.name}
        </option>
      ))}
      <option value="__new">+ New workspace</option>
    </select>
  )
}
