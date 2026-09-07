'use client'

import { useActionState } from 'react'

import { createMatterAction, type NewMatterState } from '@/app/(app)/matters/actions'
import { FormMessage } from '@/components/form-message'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const initial: NewMatterState = {}

export function NewMatterForm() {
  const [state, action, pending] = useActionState(createMatterAction, initial)
  return (
    <form action={action} className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Label htmlFor="name">Name</Label>
        <Input id="name" name="name" placeholder="Project Aurora — supplier contracts" required />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="description">Description</Label>
        <Input id="description" name="description" placeholder="Optional" />
      </div>
      <FormMessage error={state.error} />
      <Button type="submit" disabled={pending}>
        {pending ? 'Creating…' : 'Create matter'}
      </Button>
    </form>
  )
}
