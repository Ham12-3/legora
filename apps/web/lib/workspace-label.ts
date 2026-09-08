import type { Workspace } from '@/lib/types'

/**
 * Labels for the workspace switcher, disambiguated only where they need to be.
 *
 * Two workspaces can share a name: you register, which creates one, and then
 * someone adds you to theirs, which happens to be called the same thing. The
 * switcher then shows the same word twice and the only way to find the one
 * with the documents in it is to guess. Your role usually separates them;
 * where it does not, a fragment of the id always will.
 */
export function workspaceLabels(workspaces: Workspace[]): Map<string, string> {
  const tally = (key: (w: Workspace) => string) => {
    const seen = new Map<string, number>()
    for (const w of workspaces) seen.set(key(w), (seen.get(key(w)) ?? 0) + 1)
    return seen
  }
  const byName = tally((w) => w.name)
  const byNameAndRole = tally((w) => `${w.name} ${w.role}`)

  return new Map(
    workspaces.map((w) => {
      if ((byName.get(w.name) ?? 0) < 2) return [w.id, w.name]
      if ((byNameAndRole.get(`${w.name} ${w.role}`) ?? 0) < 2) {
        return [w.id, `${w.name} (${w.role})`]
      }
      return [w.id, `${w.name} (${w.role} · ${w.id.slice(0, 4)})`]
    }),
  )
}
