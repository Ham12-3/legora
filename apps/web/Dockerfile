# Production image for the Next.js server. Build context is the REPO ROOT, so
# the pnpm workspace resolves.
#
# Two stages: the builder holds pnpm, the whole workspace and the build cache;
# the runner holds the standalone output and nothing else. Because
# outputFileTracingRoot points at the repo root, the standalone tree keeps the
# workspace shape, and the server lands at apps/web/server.js.

FROM node:22-slim AS builder

RUN corepack enable
WORKDIR /repo

# Manifests first so the dependency layer caches independently of source.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
COPY packages/shared/package.json packages/shared/
RUN pnpm install --frozen-lockfile

COPY . .

# Placeholders only. lib/server/env.ts throws at import time on a missing
# secret and Next evaluates it while building. Nothing secret is baked into the
# output: every page that reads these is dynamic, and the real values are read
# from the environment when the server starts.
ENV NEXT_TELEMETRY_DISABLED=1 \
    INTERNAL_API_SECRET=build-time-placeholder \
    AUTH_SECRET=build-time-placeholder \
    API_BASE_URL=http://api:8000

RUN pnpm --filter web build


FROM node:22-slim AS runner

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

WORKDIR /app
RUN useradd --system --uid 10001 --create-home nextjs

# The standalone tree carries its own minimal node_modules. Static assets and
# public/ are deliberately not included in it and have to come along
# separately — public/ is where the pdf.js worker was copied by prebuild.
COPY --from=builder --chown=nextjs:nextjs /repo/apps/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nextjs /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder --chown=nextjs:nextjs /repo/apps/web/public ./apps/web/public

USER nextjs
EXPOSE 3000

CMD ["node", "apps/web/server.js"]
