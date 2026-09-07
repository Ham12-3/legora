'use client'

import { useActionState } from 'react'

import { addMemberAction, type AddMemberState } from '@/app/(app)/members/actions'
import { FormMessage } from '@/components/form-message'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const initial: AddMemberState = {}

export function AddMemberForm({ canGrantOwner }: { canGrantOwner: boolean }) {
  const [state, action, pending] = useActionState(addMemberAction, initial)
  return (
    <form action={action} className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Label htmlFor="email">Email</Label>
        <Input id="email" name="email" type="email" required />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="role">Role</Label>
        <select
          id="role"
          name="role"
          defaultValue="member"
          className="h-9 rounded-md border border-[var(--border)] bg-transparent px-2 text-sm"
        >
          <option value="member">Member</option>
          <option value="admin">Admin</option>
          {canGrantOwner && <option value="owner">Owner</option>}
        </select>
      </div>
      <FormMessage error={state.error} />
      {state.added && (
        <p className="text-sm text-emerald-700 dark:text-emerald-300">Added {state.added}.</p>
      )}
      <Button type="submit" disabled={pending}>
        {pending ? 'Adding…' : 'Add member'}
      </Button>
    </form>
  )
}
