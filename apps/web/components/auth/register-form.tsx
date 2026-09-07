'use client'

import { useActionState } from 'react'

import { registerAction, type RegisterState } from '@/app/(auth)/register/actions'
import { FormMessage } from '@/components/form-message'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const initial: RegisterState = {}

export function RegisterForm() {
  const [state, action, pending] = useActionState(registerAction, initial)

  return (
    <form action={action} className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Label htmlFor="workspace_name">Firm or team name</Label>
        <Input id="workspace_name" name="workspace_name" placeholder="Hale & Partners" required />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="name">Your name</Label>
        <Input id="name" name="name" autoComplete="name" required />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="email">Email</Label>
        <Input id="email" name="email" type="email" autoComplete="email" required />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="new-password"
          minLength={10}
          required
        />
        <p className="text-xs text-[var(--muted)]">At least 10 characters.</p>
      </div>
      <FormMessage error={state.error} />
      <Button type="submit" disabled={pending}>
        {pending ? 'Creating…' : 'Create workspace'}
      </Button>
    </form>
  )
}
