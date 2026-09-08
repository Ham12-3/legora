import type { Metadata } from 'next'
import Link from 'next/link'

import { auth } from '@/auth'
import { CitationScene } from '@/components/landing/citation-scene'
import { GridDemo } from '@/components/landing/grid-demo'

export const metadata: Metadata = {
  title: 'Legora — contract review in a grid',
  description:
    'Run a question down every contract in a matter and keep the sentence each answer came from.',
}

/**
 * The public front door. Signed-in visitors get the same page with the sign-up
 * links swapped for a way back into their workspace, rather than being
 * bounced: a bookmark on the bare origin should still land somewhere.
 */
export default async function Home() {
  const session = await auth()
  const signedIn = Boolean(session?.user)

  return (
    <div className="landing-root">
      <header className="landing-header">
        <div className="landing-width flex items-center justify-between gap-6 py-5">
          <span className="text-[15px] font-semibold tracking-tight">Legora</span>
          {signedIn ? (
            <Link href="/matters" className="landing-btn">
              Open workspace
            </Link>
          ) : (
            <div className="flex items-center gap-6">
              <Link href="/login" className="text-sm text-[var(--l-dim)] hover:text-[var(--l-fg)]">
                Sign in
              </Link>
              <Link href="/register" className="landing-btn">
                Create an account
              </Link>
            </div>
          )}
        </div>
      </header>

      <main>
        <section className="landing-width grid items-center gap-12 py-16 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)] lg:gap-20 lg:py-24">
          <div>
            <h1 className="text-4xl leading-[1.1] font-semibold tracking-[-0.02em] sm:text-[3.25rem]">
              Documents are rows.
              <br />
              Questions are columns.
            </h1>
            <p className="mt-7 max-w-lg text-[17px] leading-relaxed text-[var(--l-dim)]">
              Legora runs each question down every contract in the matter, and keeps the sentence
              each answer came from. Click a cell and that sentence is highlighted on the page it
              was taken from.
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-3">
              <Link
                href={signedIn ? '/matters' : '/register'}
                className="landing-btn landing-btn-lg"
              >
                {signedIn ? 'Open workspace' : 'Create an account'}
              </Link>
              {!signedIn && (
                <Link href="/login" className="landing-btn-ghost landing-btn-lg">
                  Sign in
                </Link>
              )}
            </div>
          </div>

          <CitationScene />
        </section>

        <section className="border-t border-[var(--l-rule)] bg-[var(--l-sunk)]">
          <div className="landing-width py-16">
            <GridDemo />
            <p className="mt-5 max-w-2xl text-sm leading-relaxed text-[var(--l-dim)]">
              A quote that cannot be found in the source is not shown as an answer. It keeps the
              amber bar wherever it goes: on screen, in the CSV, in the exported issues list.
            </p>
          </div>
        </section>

        <section className="landing-width py-20">
          <dl className="grid gap-x-16 gap-y-11 sm:grid-cols-2">
            <div>
              <dt className="text-sm font-semibold">Answers you can check</dt>
              <dd className="mt-2.5 text-sm leading-relaxed text-[var(--l-dim)]">
                A cell stores a verbatim span, its page, and where the words sit on that page. Where
                the quote could not be matched in the file, the answer is marked unverified instead
                of being shown as fact.
              </dd>
            </div>
            <div>
              <dt className="text-sm font-semibold">An assistant that can decline</dt>
              <dd className="mt-2.5 text-sm leading-relaxed text-[var(--l-dim)]">
                Ask across a set of documents and the reply is built only from passages retrieved
                from them, with numbered citations that open the page. If retrieval turns up nothing
                relevant it says so, and no model is called.
              </dd>
            </div>
            <div>
              <dt className="text-sm font-semibold">Your playbook</dt>
              <dd className="mt-2.5 text-sm leading-relaxed text-[var(--l-dim)]">
                Write down the preferred, fallback and unacceptable position for each point you care
                about. Run it over a contract for the position it takes, the clause, and replacement
                language, exported as a DOCX issues list.
              </dd>
            </div>
            <div>
              <dt className="text-sm font-semibold">Separate by workspace</dt>
              <dd className="mt-2.5 text-sm leading-relaxed text-[var(--l-dim)]">
                Documents, reviews and playbooks belong to a workspace, and the filter is applied
                below the route handler rather than in it. A record from another workspace is a 404,
                the same response as one that does not exist.
              </dd>
            </div>
          </dl>
        </section>
      </main>

      <footer className="border-t border-[var(--l-rule)]">
        <div className="landing-width flex flex-col gap-3 py-8 text-sm text-[var(--l-dim)] sm:flex-row sm:items-center sm:justify-between">
          <span className="font-semibold text-[var(--l-fg)]">Legora</span>
          <p>Output is a drafting aid, not legal advice. Check it against the cited source.</p>
        </div>
      </footer>
    </div>
  )
}
