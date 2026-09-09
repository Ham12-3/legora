import Link from 'next/link'

import { LocalTime } from '@/components/local-time'
import { NewPlaybookForm } from '@/components/playbook/new-playbook-form'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { workspaceApi } from '@/lib/server/api'
import type { Playbook } from '@/lib/types'

export const metadata = { title: 'Playbooks · Legora' }

export default async function PlaybooksPage() {
  const playbooks = await workspaceApi<Playbook[]>('/playbooks')

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_320px]">
      <section>
        <h1 className="text-2xl font-semibold tracking-tight">Playbooks</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Your firm&apos;s standard positions. Run one against a document to get a cited issues list
          with proposed replacement language.
        </p>
        {playbooks.length === 0 ? (
          <p className="mt-10 text-sm text-[var(--muted)]">No playbooks yet.</p>
        ) : (
          <ul className="mt-6 divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
            {playbooks.map((p) => (
              <li key={p.id}>
                <Link
                  href={`/playbooks/${p.id}`}
                  className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-900"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium">{p.name}</p>
                    {p.description && (
                      <p className="truncate text-sm text-[var(--muted)]">{p.description}</p>
                    )}
                  </div>
                  <div className="shrink-0 text-right text-xs text-[var(--muted)]">
                    <p>
                      {p.rule_count} {p.rule_count === 1 ? 'rule' : 'rules'}
                    </p>
                    <p>
                      <LocalTime iso={p.created_at} />
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
            <CardTitle>New playbook</CardTitle>
            <CardDescription>Add rules on the next screen.</CardDescription>
          </CardHeader>
          <CardContent>
            <NewPlaybookForm />
          </CardContent>
        </Card>
      </aside>
    </div>
  )
}
