'use server'

import { signIn } from '@/auth'
import { ApiError } from '@/lib/api'
import { internalApi } from '@/lib/server/api'

export type RegisterState = { error?: string }

export async function registerAction(_: RegisterState, form: FormData): Promise<RegisterState> {
  const email = String(form.get('email') ?? '').trim()
  const name = String(form.get('name') ?? '').trim()
  const password = String(form.get('password') ?? '')
  const workspaceName = String(form.get('workspace_name') ?? '').trim()

  if (password.length < 10) return { error: 'Password must be at least 10 characters.' }
  if (!workspaceName) return { error: 'Give your firm or team a name.' }

  try {
    await internalApi('/auth/register', {
      email,
      name,
      password,
      workspace_name: workspaceName,
    })
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) {
      return { error: 'An account with that email already exists.' }
    }
    return { error: error instanceof Error ? error.message : 'Registration failed.' }
  }

  // Throws a redirect on success; must stay outside the try/catch above.
  await signIn('credentials', { email, password, redirectTo: '/matters' })
  return {}
}
