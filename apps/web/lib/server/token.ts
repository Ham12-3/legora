import 'server-only'

import { SignJWT } from 'jose'

import { INTERNAL_API_SECRET } from '@/lib/server/env'

const ISSUER = 'legora-web'
const TTL = '5m'

const key = new TextEncoder().encode(INTERNAL_API_SECRET)

/**
 * Mint the internal token the API trusts. `sub` is the user, `wid` the
 * workspace they are acting in. The API verifies the signature and then
 * checks the membership row exists — the token names a workspace, the
 * database decides whether the user is in it.
 */
export async function mintInternalToken(userId: string, workspaceId?: string): Promise<string> {
  const jwt = new SignJWT(workspaceId ? { wid: workspaceId } : {})
    .setProtectedHeader({ alg: 'HS256' })
    .setIssuer(ISSUER)
    .setSubject(userId)
    .setIssuedAt()
    .setExpirationTime(TTL)
  return jwt.sign(key)
}
