"""arq worker: ingestion and review execution.

Ingestion is three chained jobs so a failure in embedding is retried without
re-parsing. Review cells run as one job per (document, group of columns);
batch runs are submitted once and polled by a cron. Transient errors retry
with backoff up to ``MAX_TRIES``; permanent ones mark the row failed at once.
Model calls happen only here, never in a request handler (CLAUDE.md rule 6).
"""

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, ClassVar

from arq import Retry, cron
from arq.connections import RedisSettings
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.ingestion import pipeline
from app.ingestion.embeddings import Embedder, get_embedder
from app.llm.client import LLMClient, get_llm_client
from app.models.review import ReviewRun, RunStatus
from app.review import batch, executor

log = logging.getLogger(__name__)

MAX_TRIES = 4
BACKOFF_SECONDS = (5, 30, 120)


def _backoff(job_try: int) -> int:
    return BACKOFF_SECONDS[min(job_try - 1, len(BACKOFF_SECONDS) - 1)]


# --- ingestion ---------------------------------------------------------------


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
            delay = _backoff(job_try)
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


# --- review -----------------------------------------------------------------


async def _bump_run(run_id: uuid.UUID, cells: int) -> None:
    async with SessionLocal() as session:
        run = await session.get(ReviewRun, run_id)
        if run is None:
            return
        run.done_cells = min(run.total_cells, run.done_cells + cells)
        if run.status is RunStatus.QUEUED:
            run.status = RunStatus.RUNNING
        if run.done_cells >= run.total_cells:
            run.status = RunStatus.DONE
            run.completed_at = datetime.now(UTC)
        await session.commit()


async def run_cells(
    ctx: dict[str, Any], run_id: str, document_id: str, column_ids: list[str]
) -> None:
    client: LLMClient = ctx["llm"]
    embedder: Embedder | None = ctx["embedder"]
    job_try = int(ctx.get("job_try", 1))
    run_uuid = uuid.UUID(run_id)

    async with SessionLocal() as session:
        run = await session.get(ReviewRun, run_uuid)
        if run is None:
            return
        review_id, force = run.review_id, run.force

    try:
        async with SessionLocal() as session:
            await executor.run_cells(
                session,
                review_id=review_id,
                document_id=uuid.UUID(document_id),
                column_ids=[uuid.UUID(c) for c in column_ids],
                force=force,
                client=client,
                embedder=embedder,
            )
    except executor.CellExecutionError as exc:
        if job_try < MAX_TRIES:
            delay = _backoff(job_try)
            log.warning(
                "run %s doc %s: try %d failed (%s); retry in %ss",
                run_id,
                document_id,
                job_try,
                exc,
                delay,
            )
            raise Retry(defer=delay) from exc
        log.error("run %s doc %s: giving up: %s", run_id, document_id, exc)
    await _bump_run(run_uuid, len(column_ids))


async def run_batch(ctx: dict[str, Any], run_id: str) -> None:
    client: LLMClient = ctx["llm"]
    embedder: Embedder | None = ctx["embedder"]
    async with SessionLocal() as session:
        run = await session.get(ReviewRun, uuid.UUID(run_id))
        if run is None:
            return
        try:
            await batch.submit_run(session, run, client=client, embedder=embedder)
        except Exception as exc:
            job_try = int(ctx.get("job_try", 1))
            if job_try < MAX_TRIES:
                raise Retry(defer=_backoff(job_try)) from exc
            run.status = RunStatus.FAILED
            run.error = f"{type(exc).__name__}: {exc}"
            await session.commit()


async def poll_batches(ctx: dict[str, Any]) -> None:
    client: LLMClient = ctx["llm"]
    embedder: Embedder | None = ctx["embedder"]
    async with SessionLocal() as session:
        runs = (
            (
                await session.execute(
                    select(ReviewRun).where(ReviewRun.status == RunStatus.SUBMITTED)
                )
            )
            .scalars()
            .all()
        )
        for run in runs:
            try:
                await batch.poll_run(session, run, client=client, embedder=embedder)
            except Exception as exc:
                log.warning("poll of run %s failed: %s", run.id, exc)


async def ping(ctx: dict[str, Any]) -> str:
    """Round-trip check that the queue is live."""
    return "pong"


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    ctx["settings"] = settings
    ctx["embedder"] = get_embedder(settings)
    ctx["llm"] = get_llm_client(settings)
    log.info(
        "worker up: llm=%s embeddings=%s ocr=%s",
        ctx["llm"].name,
        getattr(ctx["embedder"], "name", "disabled"),
        settings.ocr_enabled,
    )


async def shutdown(ctx: dict[str, Any]) -> None:
    return None


class WorkerSettings:
    """Consumed by ``arq app.worker.WorkerSettings``."""

    functions: ClassVar[list[Any]] = [
        ping,
        parse_document,
        chunk_document,
        embed_document,
        run_cells,
        run_batch,
    ]
    cron_jobs: ClassVar[list[Any]] = [cron(poll_batches, second=0, run_at_startup=False)]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 10
    max_tries = MAX_TRIES
    job_timeout = 900
    keep_result = 3600
