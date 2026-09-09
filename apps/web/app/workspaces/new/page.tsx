import Link from 'next/link'

import { NewWorkspaceForm } from '@/components/new-workspace-form'
import { resolveContext } from '@/lib/server/api'

export const metadata = { title: 'New workspace · Legora' }

export default async function NewWorkspacePage() {
  const { me } = await resolveContext()
  const hasWorkspaces = me.workspaces.length > 0

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-sm flex-col justify-center px-6 py-16">
      <p className="mb-8 text-lg font-semibold tracking-tight">Legora</p>
      <h1 className="text-2xl font-semibold tracking-tight">
        {hasWorkspaces ? 'New workspace' : 'Set up your workspace'}
      </h1>
      <p className="mt-1 text-sm text-[var(--muted)]">
        A workspace is your firm or team. Matters and documents live inside it and are never visible
        to other workspaces.
      </p>
      <div className="mt-8">
        <NewWorkspaceForm />
      </div>
      {hasWorkspaces && (
        <Link href="/matters" className="mt-6 text-sm underline underline-offset-4">
          Back to matters
        </Link>
      )}
    </main>
  )
}
