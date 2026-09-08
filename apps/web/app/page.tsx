import type { Metadata } from 'next'
import Link from 'next/link'

import { auth } from '@/auth'
import { DocumentField } from '@/components/landing/document-field'
import { GridDemo } from '@/components/landing/grid-demo'

export const metadata: Metadata = {
  title: 'Legora — contract review in a grid',
  description:
    'Legora answers your questions about a set of contracts, one column at a time, and shows you the sentence each answer came from.',
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
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-6 px-6 py-4">
          <span className="text-[15px] font-semibold tracking-tight">Legora</span>
          {signedIn ? (
            <Link href="/matters" className="landing-btn">
              Open workspace
            </Link>
          ) : (
            <div className="flex items-center gap-5">
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
        <section className="relative isolate overflow-hidden">
          <DocumentField />
          <div className="landing-veil pointer-events-none absolute inset-0" />

          <div className="relative mx-auto max-w-5xl px-6 pt-24 pb-24 sm:pt-32 sm:pb-32">
            <h1 className="max-w-3xl text-4xl leading-[1.08] font-semibold tracking-[-0.025em] sm:text-5xl">
              Contract review in a grid
            </h1>
            <p className="mt-6 max-w-xl text-[17px] leading-relaxed text-[var(--l-dim)]">
              Legora answers a question about every contract in a matter at once. Documents are
              rows, your questions are columns, and each cell carries the sentence it came from,
              located in the file before you see it.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
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
        </section>

        <section className="mx-auto max-w-5xl px-6 pb-24">
          <GridDemo />
          <p className="mt-5 max-w-2xl text-sm leading-relaxed text-[var(--l-dim)]">
            A quote that cannot be found in the source is not shown as an answer. It keeps the amber
            bar wherever it goes: on screen, in the CSV, in the exported issues list.
          </p>
        </section>

        <section className="border-t border-[var(--l-line)]">
          <div className="mx-auto grid max-w-5xl gap-x-16 gap-y-10 px-6 py-20 sm:grid-cols-2">
            <div>
              <h2 className="text-sm font-semibold">Answers you can check</h2>
              <p className="mt-3 text-sm leading-relaxed text-[var(--l-dim)]">
                Every cell stores a verbatim span, its page, and the position of the words on that
                page. Click one and the PDF opens with those words highlighted. Where the quote
                could not be matched, the answer is marked unverified rather than shown as fact.
              </p>
            </div>
            <div>
              <h2 className="text-sm font-semibold">An assistant that can decline</h2>
              <p className="mt-3 text-sm leading-relaxed text-[var(--l-dim)]">
                Ask across a set of documents and the reply is built only from passages retrieved
                from them, with numbered citations that open the page. If retrieval turns up nothing
                relevant, it says so, and no model is called.
              </p>
            </div>
            <div>
              <h2 className="text-sm font-semibold">Your playbook</h2>
              <p className="mt-3 text-sm leading-relaxed text-[var(--l-dim)]">
                Write down the preferred, fallback and unacceptable position for each point you care
                about. Run it over a contract to get the position it takes, the clause, and
                replacement language, exported as a DOCX issues list.
              </p>
            </div>
            <div>
              <h2 className="text-sm font-semibold">Separate by workspace</h2>
              <p className="mt-3 text-sm leading-relaxed text-[var(--l-dim)]">
                Documents, reviews and playbooks belong to a workspace, and the filter is applied
                below the route handler rather than in it. A record from another workspace is a 404,
                the same response as one that does not exist.
              </p>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-[var(--l-line)]">
        <div className="mx-auto flex max-w-5xl flex-col gap-3 px-6 py-8 text-sm text-[var(--l-dim)] sm:flex-row sm:items-center sm:justify-between">
          <span className="font-semibold text-[var(--l-fg)]">Legora</span>
          <p>Output is a drafting aid, not legal advice. Check it against the cited source.</p>
        </div>
      </footer>
    </div>
  )
}
