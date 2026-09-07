# Legora

An AI workspace for legal document review. Upload contracts, run a grid of
questions across them, and click every answer through to its verified source
text.

See [CLAUDE.md](./CLAUDE.md) for architecture, conventions, and commands.

## Getting started

```bash
cp .env.example .env      # add OPENAI_API_KEY when you reach Phase 3
pnpm install
uv sync --directory apps/api
pnpm dev                  # or: make dev
```

Then open http://localhost:3000, create an account (that creates your first
workspace), create a matter, and drop PDFs or DOCX files on it.

- web — http://localhost:3000
- api — http://localhost:8000/docs
- MinIO console — http://localhost:9001 (legora / legora-secret)

## Tests

```bash
pnpm test                 # or: make test
```

The API tests run against a real Postgres: they create and migrate
`legora_test` on the compose instance the first time, and truncate every table
between tests. `docker compose up -d postgres` is enough if you do not want the
whole stack.

## Regenerating API types

The web app's types come from the API's OpenAPI schema, not from hand-written
interfaces. After changing a Pydantic model:

```bash
pnpm gen:types
```

which writes `packages/shared/src/api.d.ts`. Never edit that file directly.

## Running the web app outside docker

Next.js reads `apps/web/.env.local`, not the repo-root `.env`:

```bash
cp .env apps/web/.env.local
pnpm dev:web
```
