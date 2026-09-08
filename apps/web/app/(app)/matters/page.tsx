import Link from 'next/link'

import { LocalTime } from '@/components/local-time'
import { NewMatterForm } from '@/components/matters/new-matter-form'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { workspaceApi } from '@/lib/server/api'
import type { Matter } from '@/lib/types'

export const metadata = { title: 'Matters · Legora' }

export default async function MattersPage() {
  const matters = await workspaceApi<Matter[]>('/matters')

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_320px]">
      <section>
        <h1 className="text-2xl font-semibold tracking-tight">Matters</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          A matter is a deal, case, or project. Upload its documents, then review them.
        </p>

        {matters.length === 0 ? (
          <p className="mt-10 text-sm text-[var(--muted)]">
            No matters yet. Create the first one on the right.
          </p>
        ) : (
          <ul className="mt-6 divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
            {matters.map((m) => (
              <li key={m.id}>
                <Link
                  href={`/matters/${m.id}`}
                  className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-900"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium">{m.name}</p>
                    {m.description && (
                      <p className="truncate text-sm text-[var(--muted)]">{m.description}</p>
                    )}
                  </div>
                  <div className="shrink-0 text-right text-xs text-[var(--muted)]">
                    <p>
                      {m.document_count} {m.document_count === 1 ? 'document' : 'documents'}
                    </p>
                    <p>
                      <LocalTime iso={m.created_at} />
                    </p>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <aside>
        <Card>
          <CardHeader>
            <CardTitle>New matter</CardTitle>
            <CardDescription>Documents you upload are scoped to this matter.</CardDescription>
          </CardHeader>
          <CardContent>
            <NewMatterForm />
          </CardContent>
        </Card>
      </aside>
    </div>
  )
}
