import { AddMemberForm } from '@/components/members/add-member-form'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { workspaceApi } from '@/lib/server/api'
import type { WorkspaceDetail } from '@/lib/types'

export const metadata = { title: 'Members · Legora' }

export default async function MembersPage() {
  const workspace = await workspaceApi<WorkspaceDetail>('/workspace')
  const canManage = workspace.role === 'owner' || workspace.role === 'admin'

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_320px]">
      <section>
        <h1 className="text-2xl font-semibold tracking-tight">{workspace.name}</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          {workspace.members.length} {workspace.members.length === 1 ? 'member' : 'members'}
        </p>
        <ul className="mt-6 divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
          {workspace.members.map((m) => (
            <li key={m.user_id} className="flex items-center justify-between px-4 py-3">
              <div>
                <p className="font-medium">{m.name}</p>
                <p className="text-sm text-[var(--muted)]">{m.email}</p>
              </div>
              <Badge tone={m.role === 'owner' ? 'info' : 'neutral'}>{m.role}</Badge>
            </li>
          ))}
        </ul>
      </section>

      <aside>
        <Card>
          <CardHeader>
            <CardTitle>Add a member</CardTitle>
            <CardDescription>
              {canManage
                ? 'They need an existing Legora account.'
                : 'Only owners and admins can add members.'}
            </CardDescription>
          </CardHeader>
          {canManage && (
            <CardContent>
              <AddMemberForm canGrantOwner={workspace.role === 'owner'} />
            </CardContent>
          )}
        </Card>
      </aside>
    </div>
  )
}
