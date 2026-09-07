"""Cell execution.

    plan_group    decide, for one document and up to N columns, what needs
                  asking (cache misses) and build the request
    apply_result  verify every quote, normalise every value, write cells and
                  citations, publish events
    run_cells     plan -> ask the model -> apply, for the interactive path

The batch path uses the same plan/apply pair with the provider's batch
endpoint in the middle, so both modes share one verification path.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings, get_settings
from app.ingestion.embeddings import Embedder
from app.llm.client import LLMClient
from app.llm.schema import Answer, ExtractionRequest, ExtractionResult, Question
from app.models.document import Document, DocumentStatus
from app.models.review import (
    Cell,
    CellStatus,
    Citation,
    Review,
    ReviewColumn,
)
from app.review import cache, events
from app.review.context import DocumentContext, build_context
from app.review.prompt import load_system_prompt
from app.review.values import normalize_value
from app.review.verify import verify_quote
from app.schemas.reviews import CellOut

log = logging.getLogger(__name__)


class CellExecutionError(Exception):
    """The model call failed; the affected cells are already marked failed."""


@dataclass
class GroupPlan:
    review: Review
    document: Document
    columns: list[ReviewColumn]
    cells: dict[uuid.UUID, Cell]  # column_id -> cell row (running)
    cache_keys: dict[uuid.UUID, str]
    cached: dict[uuid.UUID, Answer] = field(default_factory=dict)
    context: DocumentContext | None = None
    request: ExtractionRequest | None = None
    # question label -> column id, for answers coming back from the model
    labels: dict[str, uuid.UUID] = field(default_factory=dict)


def question_label(index: int) -> str:
    return f"q{index + 1}"


async def _get_or_create_cells(
    session: AsyncSession, review: Review, document: Document, columns: list[ReviewColumn]
) -> dict[uuid.UUID, Cell]:
    rows = (
        (
            await session.execute(
                select(Cell)
                .where(
                    Cell.review_id == review.id,
                    Cell.document_id == document.id,
                    Cell.column_id.in_([c.id for c in columns]),
                )
                .options(selectinload(Cell.citations))
            )
        )
        .scalars()
        .all()
    )
    by_column = {c.column_id: c for c in rows}
    for column in columns:
        if column.id not in by_column:
            cell = Cell(
                review_id=review.id,
                workspace_id=review.workspace_id,
                document_id=document.id,
                column_id=column.id,
                status=CellStatus.PENDING,
            )
            session.add(cell)
            by_column[column.id] = cell
    await session.flush()
    return by_column


async def publish_cell(cell: Cell) -> None:
    await events.publish(
        cell.review_id, "cell", CellOut.model_validate(cell).model_dump(mode="json")
    )


async def plan_group(
    session: AsyncSession,
    *,
    review: Review,
    document: Document,
    columns: list[ReviewColumn],
    force: bool,
    model: str,
    embedder: Embedder | None,
    settings: Settings | None = None,
) -> GroupPlan:
    settings = settings or get_settings()
    cells = await _get_or_create_cells(session, review, document, columns)
    plan = GroupPlan(
        review=review,
        document=document,
        columns=columns,
        cells=cells,
        cache_keys={
            c.id: cache.cache_key(document.sha256, c, model, settings.prompt_version)
            for c in columns
        },
    )

    for cell in cells.values():
        cell.status = CellStatus.RUNNING
        cell.error = None
    await session.commit()
    for cell in cells.values():
        await publish_cell(cell)

    if document.status is not DocumentStatus.READY:
        raise CellExecutionError(f"document is {document.status.value}, not ready")

    to_ask: list[ReviewColumn] = []
    for column in columns:
        hit = None if force else await cache.get_cached(session, plan.cache_keys[column.id])
        if hit is not None:
            plan.cached[column.id] = hit
        else:
            to_ask.append(column)

    if to_ask:
        plan.context = await build_context(
            session, document, [c.question for c in to_ask], embedder=embedder
        )
        questions: list[Question] = []
        for index, column in enumerate(to_ask):
            label = question_label(index)
            plan.labels[label] = column.id
            questions.append(
                Question(
                    label=label,
                    question=column.question,
                    output_type=column.output_type.value,
                    enum_options=tuple(column.enum_options or ()),
                )
            )
        plan.request = ExtractionRequest(
            model=model,
            system_prompt=load_system_prompt(settings.prompt_version),
            document_title=document.filename,
            outline=plan.context.outline,
            passages=plan.context.passages,
            questions=tuple(questions),
            metadata={"review_id": str(review.id), "document_id": str(document.id)},
        )
    return plan


async def apply_result(
    session: AsyncSession,
    plan: GroupPlan,
    result: ExtractionResult | None,
    *,
    model: str,
    settings: Settings | None = None,
) -> list[Cell]:
    """Verify, normalise, persist, publish. ``result`` may be None when every
    column was served from cache."""
    settings = settings or get_settings()
    answers: dict[uuid.UUID, tuple[Answer, bool]] = {
        column_id: (answer, True) for column_id, answer in plan.cached.items()
    }
    if result is not None:
        for answer in result.answers.answers:
            column_id = plan.labels.get(answer.column_id)
            if column_id is None:
                log.warning("model answered unknown question label %r", answer.column_id)
                continue
            answers[column_id] = (answer, False)
            await cache.put_cached(
                session,
                key=plan.cache_keys[column_id],
                workspace_id=plan.review.workspace_id,
                model=result.model or model,
                prompt_version=settings.prompt_version,
                answer=answer,
            )

    if plan.context is None:
        # Everything came from cache; verification still needs the text.
        plan.context = await build_context(
            session, plan.document, [], embedder=None, threshold=10**9
        )

    done: list[Cell] = []
    for column in plan.columns:
        cell = plan.cells[column.id]
        for old in list(cell.citations):
            await session.delete(old)
        cell.citations.clear()

        entry = answers.get(column.id)
        if entry is None:
            cell.status = CellStatus.FAILED
            cell.error = "model returned no answer for this question"
            done.append(cell)
            continue
        answer, from_cache = entry

        verified_any = False
        for quote in answer.quotes:
            named = plan.context.by_label.get(quote.chunk_id)
            span = verify_quote(
                quote.text,
                named,
                parsed=plan.context.parsed,
                chunks=plan.context.chunks,
                fuzzy_threshold=settings.citation_fuzzy_threshold,
            )
            if span is None:
                continue
            verified_any = True
            cell.citations.append(
                Citation(
                    workspace_id=plan.review.workspace_id,
                    chunk_id=span.chunk.id if span.chunk is not None else None,
                    quoted_text=span.quoted_text,
                    page=span.page,
                    char_start=span.char_start,
                    char_end=span.char_end,
                    bboxes=span.bboxes,
                    match_kind=span.match_kind,
                )
            )

        value_text, value_json = normalize_value(
            answer.value, column.output_type, column.enum_options
        )
        cell.status = CellStatus.DONE
        cell.not_found = answer.not_found
        cell.value_text = "" if answer.not_found else value_text
        cell.value_json = None if answer.not_found else value_json
        # A "not found" answer is verified by construction: there is nothing to
        # cite. Any other answer is verified only if at least one quote held.
        cell.verified = answer.not_found or verified_any
        cell.confidence = answer.confidence
        cell.model = (result.model if result is not None and not from_cache else None) or model
        cell.prompt_version = settings.prompt_version
        cell.cache_key = plan.cache_keys[column.id]
        cell.from_cache = from_cache
        cell.error = None
        cell.updated_at = datetime.now(UTC)
        done.append(cell)

    await session.commit()
    for cell in done:
        await session.refresh(cell, attribute_names=["citations"])
        await publish_cell(cell)
    return done


async def fail_group(session: AsyncSession, plan: GroupPlan, error: str) -> None:
    for cell in plan.cells.values():
        cell.status = CellStatus.FAILED
        cell.error = error[:2000]
    await session.commit()
    for cell in plan.cells.values():
        await publish_cell(cell)


async def run_cells(
    session: AsyncSession,
    *,
    review_id: uuid.UUID,
    document_id: uuid.UUID,
    column_ids: list[uuid.UUID],
    force: bool,
    client: LLMClient,
    embedder: Embedder | None,
    settings: Settings | None = None,
) -> list[Cell]:
    settings = settings or get_settings()
    review = await session.get(Review, review_id)
    document = await session.get(Document, document_id)
    if review is None or document is None:
        raise CellExecutionError("review or document no longer exists")
    columns = list(
        (
            await session.execute(
                select(ReviewColumn)
                .where(ReviewColumn.review_id == review.id, ReviewColumn.id.in_(column_ids))
                .order_by(ReviewColumn.ordinal)
            )
        )
        .scalars()
        .all()
    )
    if not columns:
        return []

    model = settings.model_extract
    try:
        plan = await plan_group(
            session,
            review=review,
            document=document,
            columns=columns,
            force=force,
            model=model,
            embedder=embedder,
            settings=settings,
        )
    except CellExecutionError as exc:
        cells = await _get_or_create_cells(session, review, document, columns)
        for cell in cells.values():
            cell.status = CellStatus.FAILED
            cell.error = str(exc)
        await session.commit()
        for cell in cells.values():
            await publish_cell(cell)
        return list(cells.values())

    result: ExtractionResult | None = None
    if plan.request is not None:
        try:
            result = await client.complete(plan.request)
        except Exception as exc:
            await fail_group(session, plan, f"{type(exc).__name__}: {exc}")
            raise CellExecutionError(str(exc)) from exc
        log.info(
            "review %s doc %s: %d questions, mode=%s, %d passages, %dms, %d in / %d out tokens",
            review.id,
            document.id,
            len(plan.request.questions),
            plan.context.mode if plan.context else "?",
            len(plan.request.passages),
            result.latency_ms,
            result.usage.input_tokens,
            result.usage.output_tokens,
        )
    return await apply_result(session, plan, result, model=model, settings=settings)


def group_columns(columns: list[Any], size: int | None = None) -> list[list[Any]]:
    size = size or get_settings().columns_per_call
    return [columns[i : i + size] for i in range(0, len(columns), size)]
