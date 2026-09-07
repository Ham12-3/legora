import 'server-only'

/**
 * Server-only secrets. Importing this module from a client component is a
 * build error thanks to `server-only`, which is the point.
 */

function required(name: string): string {
  const value = process.env[name]
  if (!value) throw new Error(`Missing required environment variable ${name}`)
  return value
}

export const INTERNAL_API_SECRET = required('INTERNAL_API_SECRET')
