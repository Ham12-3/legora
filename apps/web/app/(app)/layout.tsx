import Link from 'next/link'
import { redirect } from 'next/navigation'
import type { ReactNode } from 'react'

import { signOutAction } from '@/app/(app)/actions'
import { Providers } from '@/app/providers'
import { WorkspaceSwitcher } from '@/components/workspace-switcher'
import { Button } from '@/components/ui/button'
import { resolveContext } from '@/lib/server/api'

export default async function AppLayout({ children }: { children: ReactNode }) {
  const { me, active } = await resolveContext()
  if (!active) redirect('/workspaces/new')

  return (
    <Providers>
      <div className="flex min-h-screen flex-col">
        <header className="border-b border-[var(--border)]">
          <div className="mx-auto flex h-14 w-full max-w-6xl items-center gap-6 px-6">
            <Link href="/matters" className="font-semibold tracking-tight">
              Legora
            </Link>
            <WorkspaceSwitcher workspaces={me.workspaces} activeId={active.id} />
            <nav className="flex items-center gap-4 text-sm">
              <Link href="/matters" className="hover:underline underline-offset-4">
                Matters
              </Link>
              <Link href="/members" className="hover:underline underline-offset-4">
                Members
              </Link>
            </nav>
            <div className="ml-auto flex items-center gap-3 text-sm">
              <span className="text-[var(--muted)]">{me.email}</span>
              <form action={signOutAction}>
                <Button type="submit" variant="ghost" size="sm">
                  Sign out
                </Button>
              </form>
            </div>
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">{children}</main>
        <footer className="border-t border-[var(--border)] py-4 text-center text-xs text-[var(--muted)]">
          AI output is not legal advice. Verify every answer against the cited source.
        </footer>
      </div>
    </Providers>
  )
}
