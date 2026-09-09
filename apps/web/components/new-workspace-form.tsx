'use client'

import { useActionState } from 'react'

import { createWorkspaceAction, type NewWorkspaceState } from '@/app/workspaces/new/actions'
import { FormMessage } from '@/components/form-message'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const initial: NewWorkspaceState = {}

export function NewWorkspaceForm() {
  const [state, action, pending] = useActionState(createWorkspaceAction, initial)
  return (
    <form action={action} className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Label htmlFor="name">Workspace name</Label>
        <Input id="name" name="name" placeholder="Hale & Partners" required autoFocus />
      </div>
      <FormMessage error={state.error} />
      <Button type="submit" disabled={pending}>
        {pending ? 'Creating…' : 'Create workspace'}
      </Button>
    </form>
  )
}
