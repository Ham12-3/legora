"""Batch mode: the whole run as one provider batch, polled to completion.

Same ``plan_group`` / ``apply_result`` as the interactive path, so a batch cell
is verified exactly like a streamed one. The only difference is where the
model call happens.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.ingestion.embeddings import Embedder
from app.llm.client import LLMClient
from app.llm.schema import BatchItem
from app.models.document import Document
from app.models.review import Review, ReviewColumn, ReviewRun, RunStatus
from app.review.executor import (
    CellExecutionError,
    apply_result,
    fail_group,
    group_columns,
    plan_group,
)

log = logging.getLogger(__name__)


def _targets_by_document(run: ReviewRun) -> dict[uuid.UUID, list[uuid.UUID]]:
    out: dict[uuid.UUID, list[uuid.UUID]] = {}
    for document_id, column_id in run.targets:
        out.setdefault(uuid.UUID(str(document_id)), []).append(uuid.UUID(str(column_id)))
    return out


async def _load(
    session: AsyncSession, run: ReviewRun
) -> tuple[Review, dict[uuid.UUID, Document], dict[uuid.UUID, ReviewColumn]]:
    review = await session.get(Review, run.review_id)
    if review is None:
        raise CellExecutionError("review no longer exists")
    by_doc = _targets_by_document(run)
    documents = {
        d.id: d
        for d in (
            await session.execute(select(Document).where(Document.id.in_(list(by_doc))))
        ).scalars()
    }
    columns = {
        c.id: c
        for c in (
            await session.execute(select(ReviewColumn).where(ReviewColumn.review_id == review.id))
        ).scalars()
    }
    return review, documents, columns


async def submit_run(
    session: AsyncSession,
    run: ReviewRun,
    *,
    client: LLMClient,
    embedder: Embedder | None,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    review, documents, columns = await _load(session, run)
    model = settings.model_extract

    items: list[BatchItem] = []
    plan_index: dict[str, dict[str, object]] = {}
    served_from_cache = 0
    for document_id, column_ids in _targets_by_document(run).items():
        document = documents.get(document_id)
        cols = [columns[c] for c in column_ids if c in columns]
        if document is None or not cols:
            continue
        for group in group_columns(cols, settings.columns_per_call):
            try:
                plan = await plan_group(
                    session,
                    review=review,
                    document=document,
                    columns=group,
                    force=run.force,
                    model=model,
                    embedder=embedder,
                    settings=settings,
                )
            except CellExecutionError as exc:
                log.warning("batch: skipping %s: %s", document.id, exc)
                continue
            if plan.request is None:
                await apply_result(session, plan, None, model=model, settings=settings)
                served_from_cache += len(group)
                continue
            custom_id = f"{run.id.hex[:12]}-{len(items):05d}"
            items.append(BatchItem(custom_id=custom_id, request=plan.request))
            plan_index[custom_id] = {
                "document_id": str(document.id),
                "column_ids": [str(c.id) for c in group],
            }

    run.done_cells = served_from_cache
    if not items:
        run.status = RunStatus.DONE
        run.completed_at = datetime.now(UTC)
        await session.commit()
        return

    run.provider_batch_id = await client.batch_submit(items)
    run.batch_plan = plan_index
    run.status = RunStatus.SUBMITTED
    await session.commit()
    log.info(
        "run %s: submitted batch %s with %d requests", run.id, run.provider_batch_id, len(items)
    )


async def poll_run(
    session: AsyncSession,
    run: ReviewRun,
    *,
    client: LLMClient,
    embedder: Embedder | None,
    settings: Settings | None = None,
) -> bool:
    """Returns True when the run reached a terminal state."""
    settings = settings or get_settings()
    if run.status is not RunStatus.SUBMITTED or not run.provider_batch_id:
        return True
    status = await client.batch_poll(run.provider_batch_id)
    if not status.completed and not status.failed:
        return False

    review, documents, columns = await _load(session, run)
    model = settings.model_extract
    for custom_id, spec in run.batch_plan.items():
        document = documents.get(uuid.UUID(str(spec["document_id"])))
        cols = [
            columns[uuid.UUID(str(c))] for c in spec["column_ids"] if uuid.UUID(str(c)) in columns
        ]
        if document is None or not cols:
            continue
        # force=True: the answer is in hand, do not consult the cache again.
        plan = await plan_group(
            session,
            review=review,
            document=document,
            columns=cols,
            force=True,
            model=model,
            embedder=embedder,
            settings=settings,
        )
        if status.failed:
            await fail_group(session, plan, f"batch {status.detail}")
            continue
        result = status.results.get(custom_id)
        if result is None:
            await fail_group(
                session, plan, status.errors.get(custom_id, "missing from batch output")
            )
            continue
        await apply_result(session, plan, result, model=model, settings=settings)
        run.done_cells += len(cols)

    run.status = RunStatus.FAILED if status.failed else RunStatus.DONE
    run.error = status.detail if status.failed else None
    run.completed_at = datetime.now(UTC)
    await session.commit()
    return True
