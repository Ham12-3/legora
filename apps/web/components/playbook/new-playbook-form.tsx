'use client'

import { useActionState } from 'react'

import { createPlaybookAction, type NewPlaybookState } from '@/app/(app)/playbooks/actions'
import { FormMessage } from '@/components/form-message'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const initial: NewPlaybookState = {}

export function NewPlaybookForm() {
  const [state, action, pending] = useActionState(createPlaybookAction, initial)
  return (
    <form action={action} className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Label htmlFor="pb-name">Name</Label>
        <Input
          id="pb-name"
          name="name"
          placeholder="Supplier paper — standard positions"
          required
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="pb-description">Description</Label>
        <Input id="pb-description" name="description" placeholder="Optional" />
      </div>
      <FormMessage error={state.error} />
      <Button type="submit" disabled={pending}>
        {pending ? 'Creating…' : 'Create playbook'}
      </Button>
    </form>
  )
}
