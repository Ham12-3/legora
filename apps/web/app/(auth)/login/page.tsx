import Link from 'next/link'

import { LoginForm } from '@/components/auth/login-form'

export const metadata = { title: 'Sign in · Legora' }

export default function LoginPage() {
  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
      <p className="mt-1 text-sm text-[var(--muted)]">
        New here?{' '}
        <Link href="/register" className="underline underline-offset-4">
          Create an account
        </Link>
      </p>
      <div className="mt-8">
        <LoginForm />
      </div>
    </>
  )
}
