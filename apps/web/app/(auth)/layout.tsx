import type { ReactNode } from 'react'

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-sm flex-col justify-center px-6 py-16">
      <p className="mb-8 text-lg font-semibold tracking-tight">Legora</p>
      {children}
    </main>
  )
}
