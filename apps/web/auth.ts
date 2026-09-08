/**
 * Auth.js configuration.
 *
 * Auth.js owns the browser session only. Users, passwords, and workspaces
 * live in the FastAPI service: `authorize()` calls its `/auth/login`, which
 * is gated by the internal secret so nothing but this server can reach it.
 * No database adapter — the session is a signed JWT carrying the user id.
 */

import NextAuth, { type DefaultSession } from 'next-auth'
import Credentials from 'next-auth/providers/credentials'

import { apiUrl } from '@/lib/api'
import { INTERNAL_API_SECRET } from '@/lib/server/env'

declare module 'next-auth' {
  interface Session {
    user: { id: string; email: string; name: string } & DefaultSession['user']
  }
}

// Prefixes anyone may reach. "/" is matched exactly, not as a prefix, or it
// would open the whole app.
const PUBLIC_PATHS = ['/login', '/register']
const PUBLIC_EXACT = ['/']

type ApiUser = { id: string; email: string; name: string }

export const { handlers, auth, signIn, signOut } = NextAuth({
  session: { strategy: 'jwt' },
  pages: { signIn: '/login' },
  trustHost: true,
  providers: [
    Credentials({
      credentials: {
        email: { label: 'Email', type: 'email' },
        password: { label: 'Password', type: 'password' },
      },
      async authorize(credentials) {
        const email = typeof credentials.email === 'string' ? credentials.email : ''
        const password = typeof credentials.password === 'string' ? credentials.password : ''
        if (!email || !password) return null

        const response = await fetch(apiUrl('/auth/login'), {
          method: 'POST',
          headers: {
            'content-type': 'application/json',
            'x-internal-secret': INTERNAL_API_SECRET,
          },
          body: JSON.stringify({ email, password }),
          cache: 'no-store',
        })
        if (!response.ok) return null

        const user = (await response.json()) as ApiUser
        return { id: user.id, email: user.email, name: user.name }
      },
    }),
  ],
  callbacks: {
    jwt({ token, user }) {
      if (user?.id) token.sub = user.id
      return token
    },
    session({ session, token }) {
      if (token.sub) session.user.id = token.sub
      return session
    },
    authorized({ auth, request }) {
      const { pathname } = request.nextUrl
      const isPublic =
        PUBLIC_EXACT.includes(pathname) || PUBLIC_PATHS.some((p) => pathname.startsWith(p))
      if (isPublic) return true
      return Boolean(auth?.user)
    },
  },
})
