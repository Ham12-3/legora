export { auth as middleware } from '@/auth'

export const config = {
  // Everything except Auth.js's own routes, Next internals, and static files
  // (including the pdf.js worker copied into public/).
  matcher: [
    '/((?!api/auth|_next/static|_next/image|favicon.ico|pdf.min.mjs|pdf.worker.min.mjs|.*\\.(?:svg|png|jpg|ico)$).*)',
  ],
}
