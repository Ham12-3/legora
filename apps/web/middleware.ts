export { auth as middleware } from '@/auth'

export const config = {
  // Everything except Auth.js's own routes, Next internals, and static files.
  matcher: ['/((?!api/auth|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|ico)$).*)'],
}
