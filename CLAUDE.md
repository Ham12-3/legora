# Project: Legora

An AI workspace for legal document review. The core feature is Tabular Review:
documents as rows, questions as columns, every answer traceable to source.

## Structure

- `apps/web` — Next.js 15 App Router, TypeScript, Tailwind, shadcn/ui
- `apps/api` — FastAPI, SQLAlchemy 2.0, Alembic, arq workers
- `packages/shared` — shared TypeScript types generated from Pydantic models
- `docker-compose.yml` — Postgres 17 + pgvector, Redis 7, MinIO (S3-compatible)

## Non-negotiable rules

1. Every table has `workspace_id`. Every query filters on it. Enforced in the
   repository base class. Never trust the route handler.
2. Every AI-generated claim carries a verbatim quote plus a chunk id, and is
   verified by string match in Python before it reaches the UI. Unverified
   answers are visually distinct from verified ones. Structured Outputs
   guarantees shape, not truth.
3. Character offsets round-trip: `source_text[char_start:char_end] == chunk.text`.
4. No new abstraction until the third repetition.
5. Prompts live in `apps/api/prompts/` as versioned files. Changing a prompt
   means bumping `PROMPT_VERSION`, which invalidates the cell cache.
6. Nothing calls a model in a request handler. Model calls happen in workers or
   in explicitly streamed endpoints.
7. `OPENAI_API_KEY` exists only in the FastAPI service. Never in the web bundle,
   never under a `NEXT_PUBLIC_` prefix.
8. Extraction prompt order is fixed for prompt caching: system instructions,
   then playbook, then document content, then the questions LAST. Questions
   first turns every cell in a column into a cache miss.

## Fixed constants

- `EMBED_DIM = 1536` — `text-embedding-3-large` called with `dimensions: 1536`.
  pgvector's HNSW and IVFFlat indexes cap at 2000 dimensions, so the model's
  native 3072 cannot be indexed directly. This number is baked into the
  `chunks.embedding` column type. Changing it means re-embedding everything.
- Model ids are environment config keyed by role (`MODEL_ROUTER`,
  `MODEL_EXTRACT`, `MODEL_SYNTH`). Never inline a model id. Log the model id on
  every cell so eval results stay interpretable after a swap.

## Commands

`make` is canonical; every target is mirrored as a pnpm script for machines
without GNU make.

| Task | make | pnpm |
|---|---|---|
| install deps | `make install` | `pnpm install` |
| run everything | `make dev` | `pnpm dev` |
| tests | `make test` | `pnpm test` |
| lint + types | `make lint` | `pnpm lint` |
| migrations | `make migrate` | `pnpm migrate` |
| eval harness | `make eval` | `pnpm eval` |

## Style

- Python: ruff, mypy strict, no `Any` without a comment explaining why.
- TypeScript: no `any`, no default exports except pages.
- Tests colocated with the code they cover. pytest and vitest.
