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

## How a request is authenticated

Auth.js has no organisations, so tenancy is ours.

1. Auth.js (Credentials provider, JWT session, no adapter) owns the browser
   session only. `authorize()` calls the API's `POST /auth/login`, which is
   gated by `X-Internal-Secret` so nothing but the Next.js server can reach it.
   Users, password hashes, workspaces and memberships all live in the API.
2. Every API call from Next.js carries a 5-minute HS256 **internal JWT**
   (`sub` = user id, `wid` = active workspace) minted in
   `apps/web/lib/server/token.ts` with `INTERNAL_API_SECRET`.
3. The API verifies the signature, then `get_principal` checks a membership
   row exists for (`sub`, `wid`). The token asserts intent; the database
   decides. A valid token naming a workspace you are not in is a 403.
4. Routes take the workspace from the principal, never from the path. A
   cross-workspace id is a 404, indistinguishable from a missing row.
5. The active workspace is the `legora_ws` cookie, set only by server actions
   that first confirm membership. Client components never hold a token: they
   call `/api/proxy/*`, which mints one server-side and forwards.

`apps/api/tests/test_tenancy_isolation.py` parametrises over every route with
`{matter_id}` or `{document_id}` and fails if a new one lands without an entry.

## How upload works

presign -> browser PUTs straight to object storage -> register. The browser
hashes the file first; a sha256 already in the matter is reported at presign
so duplicate bytes never move. `storage_key` is derived server-side from
(workspace, matter, document id) and compared on register, so a client cannot
point a row at another tenant's object. The (matter_id, sha256) unique
constraint arbitrates races; the loser's object is deleted.

## How ingestion works

Three arq jobs, chained: `parse_document` -> `chunk_document` -> `embed_document`
(`apps/api/app/worker.py`). Each stage reads only the database and is retried
on its own; a permanent `IngestionError` marks the document failed with the
reason. `POST /documents/{id}/reingest` resets and re-queues.

- **Parse** (`ingestion/pdf.py`, `ingestion/docx.py`): page text is *built
  from the words*, so every word's offset into the page is exact by
  construction. Words within a line join with " ", lines with "\n",
  paragraphs with `BLOCK_SEPARATOR` ("\n\n"). A page with fewer than
  `ocr_min_chars_per_page` extractable characters is treated as scanned: OCR
  via Tesseract if available, and `is_ocr` is set either way so the UI warns.
  Rows land in `document_pages` with `words = [[start, end, x0, y0, x1, y1]]`.
- **Offsets are document-global.** `document_text = "\n".join(page.text)` and
  every chunk's `char_start/char_end` index into that. `pipeline.load_parsed`
  rebuilds it from `document_pages`; the citation verifier will use the same
  function, so chunker and verifier can never disagree about the text.
- **Chunk** (`ingestion/chunker.py`): blocks are re-derived from page text by
  splitting on `BLOCK_SEPARATOR`. `sections.py` classifies headings by depth
  (0 = ARTICLE/PART/all-caps, 1 = "8.", 2 = "8.2", 3 = "(a)", 4 = "(i)").
  Depth <= 1 headings open a section; a section that fits `chunk_target_tokens`
  is never split, small sections under the same ARTICLE pack together, an
  oversized section splits on clause boundaries and never runs into the next.
  `section_path` is the deepest heading path common to the whole chunk.
  Overlap moves `char_start` backwards one sentence, so the slice invariant
  survives.
- **Embed** (`ingestion/embeddings.py`): `EMBEDDINGS_PROVIDER` = auto | openai |
  fake | none. `auto` is OpenAI when a key is set, otherwise skip — chunks still
  land and the document still reaches `ready`. Batches of `embed_batch_size`,
  committed per batch. The embedded text is `section_path + "\n" + chunk.text`;
  `chunk.text` itself stays an exact slice.

Fixtures: `tests/fixtures/*.pdf|docx` are generated by
`tests/fixtures/build_fixtures.py` — five real-shaped contracts covering the
numbering conventions, one DOCX, one image-only "scan". Regenerate only when
the templates change.

## How a cell is computed

`apps/api/app/review/executor.py`, reached from the `run_cells` worker job.

1. `POST /reviews/{id}/run` records a `review_runs` row, marks the target
   cells `pending`, and enqueues one job per (document, group of <= 6
   columns). Mode `auto` picks the Batch API above `batch_threshold_cells`.
2. `plan_group`: mark cells `running`; compute each column's cache key
   (document sha256, question, output type, options, model, prompt version);
   columns with a cached answer skip the model. For the rest,
   `context.build_context` routes: whole document if under
   `full_context_token_threshold`, otherwise hybrid retrieval (pgvector cosine
   + `ts_rank_cd`, fused by reciprocal rank, top-k plus neighbours) with a
   structural outline of every section so the model knows what it cannot see.
3. The prompt (`review/prompt.py`) is rendered in a fixed order: system
   instructions from `prompts/extract_cells.<version>.md`, playbook, document
   passages labelled `c<ordinal>`, questions LAST as `q1..qN`. Structured
   Outputs with the strict schema in `llm/schema.py`.
4. `apply_result`: every quote is located in the source by
   `review/verify.py` — exact in the named passage, else exact anywhere in the
   document (`relocated`), else fuzzy in the named passage at >= 0.9. The
   citation stores the *source* slice with document-global offsets, page, and
   word boxes. A quote that matches nowhere is dropped. `cell.verified` is
   true only if at least one quote held (or the answer is `not_found`).
   Values are typed by `review/values.py`. Cells and citations are written,
   the answer is cached, and a `cell` event is published to Redis for SSE.
5. Batch mode (`review/batch.py`) is the same `plan_group`/`apply_result`
   pair around the provider's batch endpoint; there is one verification path.

`LLM_PROVIDER=auto` falls back to `llm/fake.py` when no key is set. The fake
answers by keyword overlap and quotes verbatim, so every path runs offline;
its cells are `model="fake"` and the review detail sets `demo_mode`.

## How the assistant answers

`apps/api/app/assistant/service.py::answer_stream`, behind
`POST /threads/{id}/messages` — the one model call outside the worker, allowed
because the endpoint is explicitly streamed (rule 6). Events: `message` (the
stored user turn), `status`, `delta` (answer prose as written), `message` (the
final assistant turn), `error`.

1. `retrieval.retrieve_across` runs lexical (`websearch_to_tsquery` with the
   question's words OR-ed — AND semantics would hide every hit when one word is
   missing) and vector (pgvector cosine, only within
   `assistant_vector_max_distance`) search across the thread's ready documents,
   fuses by reciprocal rank, reranks by lexical overlap, adds neighbours of the
   strongest hits, and labels passages `d<doc>c<ordinal>`.
2. **No hits means refusal.** The assistant stores a fixed "couldn't find
   anything" message with `insufficient=true` and the model is never called.
   `tests/assistant` proves the model call count stays at zero.
3. Otherwise the prompt (`prompts/assistant.<version>.md`) is rendered system,
   passages, history, question LAST, with Structured Outputs
   (`CHAT_ANSWER_SCHEMA`: answer, numbered citations, insufficient). The
   `answer` field is streamed out of the partial JSON by
   `assistant/stream.py`.
4. Every citation is verified with the same `review/verify.py` used by the
   grid. Unverified quotes are dropped and their `[n]` markers removed from
   the prose; the message is `verified=false` if any marker lost its source.
   The model's own `insufficient` judgement is kept, never overridden.

## Frontend notes

- The review grid (`apps/web/components/review/review-grid.tsx`) keeps the
  `ReviewDetail` in TanStack Query and merges `cell` events from
  `/api/proxy/reviews/{id}/stream` (SSE through the Next proxy) into it;
  a slow poll is the fallback while cells are in flight.
- `CellView` renders unverified answers with an amber bar and a warning label.
  Do not "simplify" this into an icon: rule 2.
- pdf.js is NOT bundled. Its build is itself a webpack bundle and breaks when
  re-bundled by Next in dev ("Object.defineProperty called on non-object").
  `apps/web/scripts/copy-pdf-worker.mjs` (predev/prebuild) copies
  `pdf.min.mjs` and `pdf.worker.min.mjs` into `public/`, the viewer loads them
  with a native `import()`, and the middleware matcher exempts them. Citation
  bboxes are PyMuPDF points with a top-left origin, same as pdf.js viewports,
  so a highlight is `box * (renderedWidth / pageWidth)`.
- Everything the browser fetches from the API goes through `/api/proxy/*`,
  whose prefix allowlist must include any new router prefix. Forgetting this
  fails silently as a 404 from the proxy.
- The chat posts the question and reads the SSE reply from the fetch body
  (`lib/sse.ts`) because EventSource cannot POST. `[n]` markers render as
  chips bound to verified citations; a marker with no citation stays plain.

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
