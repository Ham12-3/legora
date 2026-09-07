"""arq worker: the ingestion pipeline as three chained jobs.

Each stage is its own job so a failure in embedding (a rate limit, say) is
retried without re-parsing the PDF. Transient errors retry with backoff up to
``max_tries``; ``IngestionError`` is permanent and marks the document failed
at once. Model calls (embeddings today, extraction from Phase 3) happen only
here, never in a request handler.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

from arq import Retry
from arq.connections import RedisSettings

from app.config import get_settings
from app.db import SessionLocal
from app.ingestion import pipeline
from app.ingestion.embeddings import Embedder, get_embedder

log = logging.getLogger(__name__)

MAX_TRIES = 4
BACKOFF_SECONDS = (5, 30, 120)


async def _run_stage(
    ctx: dict[str, Any],
    document_id: str,
    stage: Callable[[uuid.UUID], Awaitable[None]],
    next_job: str | None,
) -> None:
    doc_id = uuid.UUID(document_id)
    job_try = int(ctx.get("job_try", 1))
    try:
        await stage(doc_id)
    except pipeline.IngestionError as exc:
        log.warning("document %s: permanent failure: %s", doc_id, exc)
        async with SessionLocal() as session:
            await pipeline.mark_failed(session, doc_id, str(exc))
        return
    except Exception as exc:
        if job_try < MAX_TRIES:
            delay = BACKOFF_SECONDS[min(job_try - 1, len(BACKOFF_SECONDS) - 1)]
            log.warning(
                "document %s: try %d failed (%s); retrying in %ss", doc_id, job_try, exc, delay
            )
            raise Retry(defer=delay) from exc
        log.error("document %s: giving up after %d tries: %s", doc_id, job_try, exc)
        async with SessionLocal() as session:
            await pipeline.mark_failed(session, doc_id, f"{type(exc).__name__}: {exc}")
        return

    if next_job:
        await ctx["redis"].enqueue_job(next_job, document_id)


async def parse_document(ctx: dict[str, Any], document_id: str) -> None:
    async def stage(doc_id: uuid.UUID) -> None:
        async with SessionLocal() as session:
            await pipeline.run_parse(session, doc_id, pipeline.storage_loader)

    await _run_stage(ctx, document_id, stage, "chunk_document")


async def chunk_document(ctx: dict[str, Any], document_id: str) -> None:
    async def stage(doc_id: uuid.UUID) -> None:
        async with SessionLocal() as session:
            await pipeline.run_chunk(session, doc_id)

    await _run_stage(ctx, document_id, stage, "embed_document")


async def embed_document(ctx: dict[str, Any], document_id: str) -> None:
    embedder: Embedder | None = ctx["embedder"]

    async def stage(doc_id: uuid.UUID) -> None:
        async with SessionLocal() as session:
            await pipeline.run_embed(session, doc_id, embedder)

    await _run_stage(ctx, document_id, stage, None)


async def ping(ctx: dict[str, Any]) -> str:
    """Round-trip check that the queue is live."""
    return "pong"


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    ctx["settings"] = settings
    ctx["embedder"] = get_embedder(settings)
    log.info(
        "worker up: embeddings=%s ocr=%s",
        getattr(ctx["embedder"], "name", "disabled"),
        settings.ocr_enabled,
    )


async def shutdown(ctx: dict[str, Any]) -> None:
    return None


class WorkerSettings:
    """Consumed by ``arq app.worker.WorkerSettings``."""

    functions: ClassVar[list[Any]] = [ping, parse_document, chunk_document, embed_document]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 10
    max_tries = MAX_TRIES
    job_timeout = 900
    # Parsing a large PDF can hold the worker for a while; keep results so a
    # failed chain is inspectable in Redis for an hour.
    keep_result = 3600
