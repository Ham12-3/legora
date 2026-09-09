import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Monorepo: let Next trace files from the repo root, not apps/web.
  outputFileTracingRoot: new URL('../..', import.meta.url).pathname,
  // Emit .next/standalone so the production image ships a server and only the
  // node_modules it actually traced, instead of the whole workspace. Only
  // affects `next build`; `next dev` is unchanged.
  output: 'standalone',
}

export default nextConfig
