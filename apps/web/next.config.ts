import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Monorepo: let Next trace files from the repo root, not apps/web.
  outputFileTracingRoot: new URL('../..', import.meta.url).pathname,
}

export default nextConfig
