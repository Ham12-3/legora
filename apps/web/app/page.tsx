import { apiFetch, API_BASE_URL } from '@/lib/api'

type Readiness = {
  status: 'ready' | 'degraded'
  postgres: boolean
  redis: boolean
}

async function getReadiness(): Promise<Readiness | null> {
  try {
    return await apiFetch<Readiness>('/readyz')
  } catch {
    return null
  }
}

function Dot({ ok }: { ok: boolean }) {
  return (
    <span
      aria-hidden
      className={`inline-block size-2 rounded-full ${ok ? 'bg-emerald-500' : 'bg-red-500'}`}
    />
  )
}

function Row({ label, ok }: { label: string; ok: boolean }) {
  return (
    <li className="flex items-center gap-3 py-2">
      <Dot ok={ok} />
      <span className="flex-1">{label}</span>
      <span className="text-[var(--muted)] font-mono text-xs">{ok ? 'up' : 'down'}</span>
    </li>
  )
}

export default async function Home() {
  const readiness = await getReadiness()

  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center px-6 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">Legora</h1>
      <p className="text-[var(--muted)] mt-2 text-sm">
        AI workspace for legal document review. Phase 0 — skeleton only.
      </p>

      <ul className="mt-8 divide-y" style={{ borderColor: 'var(--border)' }}>
        <Row label="API" ok={readiness !== null} />
        <Row label="Postgres" ok={readiness?.postgres ?? false} />
        <Row label="Redis" ok={readiness?.redis ?? false} />
      </ul>

      <p className="text-[var(--muted)] mt-8 font-mono text-xs">{API_BASE_URL}</p>
    </main>
  )
}
