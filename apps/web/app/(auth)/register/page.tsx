import Link from 'next/link'

import { RegisterForm } from '@/components/auth/register-form'

export const metadata = { title: 'Create account · Legora' }

export default function RegisterPage() {
  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">Create your workspace</h1>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Already have an account?{' '}
        <Link href="/login" className="underline underline-offset-4">
          Sign in
        </Link>
      </p>
      <div className="mt-8">
        <RegisterForm />
      </div>
    </>
  )
}
