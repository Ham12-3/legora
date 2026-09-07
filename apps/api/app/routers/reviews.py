"""Tabular Review endpoints.

Nothing here calls a model. ``run`` records what to compute and hands it to
the worker; ``stream`` relays the worker's cell events as SSE.
"""

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.auth.deps import CurrentPrincipal, DbSession
from app.config import get_settings
from app.errors import ConflictError, NotFoundError
from app.models.document import Document
from app.models.review import (
    Cell,
    CellStatus,
    Review,
    ReviewColumn,
    ReviewDocument,
    ReviewRun,
    RunMode,
    RunStatus,
)
from app.queue import enqueue
from app.repositories.base import WorkspaceScopedRepository
from app.repositories.documents import DocumentRepository
from app.repositories.matters import MatterRepository
from app.review import events, export
from app.review.executor import group_columns, publish_cell
from app.schemas.reviews import (
    AddDocumentsRequest,
    CellOut,
    ColumnCreate,
    ColumnOut,
    ColumnUpdate,
    ReviewCreate,
    ReviewDetail,
    ReviewDocumentOut,
    ReviewOut,
    RunOut,
    RunRequest,
)

router = APIRouter(prefix="/reviews", tags=["reviews"])


class ReviewRepository(WorkspaceScopedRepository[Review]):
    model = Review

    async def get_full(self, review_id: uuid.UUID) -> Review:
        stmt = (
            self.scoped()
            .where(Review.id == review_id)
            .options(selectinload(Review.documents), selectinload(Review.columns))
        )
        review = (await self.session.execute(stmt)).scalar_one_or_none()
        if review is None:
            raise NotFoundError("review")
        return review


def _review_out(review: Review) -> ReviewOut:
    return ReviewOut(
        id=review.id,
        matter_id=review.matter_id,
        name=review.name,
        created_at=review.created_at,
        document_count=len(review.documents),
        column_count=len(review.columns),
    )


# --- reviews ----------------------------------------------------------------


@router.get("", response_model=list[ReviewOut])
async def list_reviews(
    principal: CurrentPrincipal,
    session: DbSession,
    matter_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[ReviewOut]:
    repo = ReviewRepository(session, principal.workspace_id)
    stmt = repo.scoped().options(selectinload(Review.documents), selectinload(Review.columns))
    if matter_id is not None:
        stmt = stmt.where(Review.matter_id == matter_id)
    rows = (await session.execute(stmt.order_by(Review.created_at.desc()))).scalars().all()
    return [_review_out(r) for r in rows]


@router.post("", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
async def create_review(
    body: ReviewCreate, principal: CurrentPrincipal, session: DbSession
) -> ReviewOut:
    await MatterRepository(session, principal.workspace_id).get(body.matter_id)
    docs = DocumentRepository(session, principal.workspace_id)
    documents = [await docs.get(d) for d in body.document_ids]
    for d in documents:
        if d.matter_id != body.matter_id:
            raise ConflictError(f"document {d.id} belongs to another matter")

    review = Review(
        workspace_id=principal.workspace_id,
        matter_id=body.matter_id,
        name=body.name,
        created_by=principal.user_id,
    )
    ReviewRepository(session, principal.workspace_id).add(review)
    await session.flush()
    for order, d in enumerate(documents):
        session.add(ReviewDocument(review_id=review.id, document_id=d.id, row_order=order))
    await session.commit()
    review = await ReviewRepository(session, principal.workspace_id).get_full(review.id)
    return _review_out(review)


@router.get("/{review_id}", response_model=ReviewDetail)
async def get_review(
    review_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> ReviewDetail:
    review = await ReviewRepository(session, principal.workspace_id).get_full(review_id)

    doc_ids = [rd.document_id for rd in review.documents]
    documents = {
        d.id: d
        for d in (
            await session.execute(
                DocumentRepository(session, principal.workspace_id)
                .scoped()
                .where(Document.id.in_(doc_ids))
            )
        ).scalars()
    }
    cells = (
        (
            await session.execute(
                select(Cell)
                .where(Cell.review_id == review.id, Cell.workspace_id == principal.workspace_id)
                .options(selectinload(Cell.citations))
            )
        )
        .scalars()
        .all()
    )
    runs = (
        (
            await session.execute(
                select(ReviewRun)
                .where(ReviewRun.review_id == review.id)
                .order_by(ReviewRun.created_at.desc())
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    return ReviewDetail(
        review=_review_out(review),
        documents=[
            ReviewDocumentOut(
                document_id=rd.document_id,
                filename=documents[rd.document_id].filename,
                mime_type=documents[rd.document_id].mime_type,
                status=documents[rd.document_id].status,
                page_count=documents[rd.document_id].page_count,
                row_order=rd.row_order,
            )
            for rd in review.documents
            if rd.document_id in documents
        ],
        columns=[ColumnOut.model_validate(c) for c in review.columns],
        cells=[CellOut.model_validate(c) for c in cells],
        runs=[RunOut.model_validate(r) for r in runs],
        demo_mode=any(c.model == "fake" for c in cells),
    )


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review(
    review_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> None:
    await ReviewRepository(session, principal.workspace_id).delete(review_id)
    await session.commit()


# --- rows -------------------------------------------------------------------


@router.post("/{review_id}/documents", response_model=list[ReviewDocumentOut])
async def add_documents(
    review_id: uuid.UUID,
    body: AddDocumentsRequest,
    principal: CurrentPrincipal,
    session: DbSession,
) -> list[ReviewDocumentOut]:
    review = await ReviewRepository(session, principal.workspace_id).get_full(review_id)
    docs = DocumentRepository(session, principal.workspace_id)
    existing = {rd.document_id for rd in review.documents}
    order = max((rd.row_order for rd in review.documents), default=-1) + 1
    added: list[Document] = []
    for document_id in body.document_ids:
        document = await docs.get(document_id)
        if document.matter_id != review.matter_id:
            raise ConflictError(f"document {document.id} belongs to another matter")
        if document.id in existing:
            continue
        session.add(ReviewDocument(review_id=review.id, document_id=document.id, row_order=order))
        order += 1
        added.append(document)
    await session.commit()
    return [
        ReviewDocumentOut(
            document_id=d.id,
            filename=d.filename,
            mime_type=d.mime_type,
            status=d.status,
            page_count=d.page_count,
            row_order=i,
        )
        for i, d in enumerate(added)
    ]


@router.delete("/{review_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_document(
    review_id: uuid.UUID,
    document_id: uuid.UUID,
    principal: CurrentPrincipal,
    session: DbSession,
) -> None:
    review = await ReviewRepository(session, principal.workspace_id).get_full(review_id)
    row = next((rd for rd in review.documents if rd.document_id == document_id), None)
    if row is None:
        raise NotFoundError("document")
    await session.delete(row)
    for cell in (
        await session.execute(
            select(Cell).where(Cell.review_id == review.id, Cell.document_id == document_id)
        )
    ).scalars():
        await session.delete(cell)
    await session.commit()


# --- columns ----------------------------------------------------------------


@router.post("/{review_id}/columns", response_model=ColumnOut, status_code=status.HTTP_201_CREATED)
async def add_column(
    review_id: uuid.UUID, body: ColumnCreate, principal: CurrentPrincipal, session: DbSession
) -> ColumnOut:
    review = await ReviewRepository(session, principal.workspace_id).get_full(review_id)
    column = ReviewColumn(
        review_id=review.id,
        workspace_id=principal.workspace_id,
        name=body.name,
        question=body.question,
        output_type=body.output_type,
        enum_options=body.enum_options,
        ordinal=max((c.ordinal for c in review.columns), default=-1) + 1,
    )
    session.add(column)
    await session.commit()
    await session.refresh(column)
    return ColumnOut.model_validate(column)


async def _column(
    session: DbSession, principal: CurrentPrincipal, review_id: uuid.UUID, column_id: uuid.UUID
) -> ReviewColumn:
    await ReviewRepository(session, principal.workspace_id).get(review_id)
    column = (
        await session.execute(
            select(ReviewColumn).where(
                ReviewColumn.id == column_id,
                ReviewColumn.review_id == review_id,
                ReviewColumn.workspace_id == principal.workspace_id,
            )
        )
    ).scalar_one_or_none()
    if column is None:
        raise NotFoundError("column")
    return column


@router.patch("/{review_id}/columns/{column_id}", response_model=ColumnOut)
async def update_column(
    review_id: uuid.UUID,
    column_id: uuid.UUID,
    body: ColumnUpdate,
    principal: CurrentPrincipal,
    session: DbSession,
) -> ColumnOut:
    column = await _column(session, principal, review_id, column_id)
    changed_question = False
    if body.name is not None:
        column.name = body.name
    if body.question is not None and body.question != column.question:
        column.question = body.question
        changed_question = True
    if body.output_type is not None and body.output_type is not column.output_type:
        column.output_type = body.output_type
        changed_question = True
    if body.enum_options is not None:
        column.enum_options = body.enum_options
        changed_question = True
    if changed_question:
        # Existing answers no longer answer this question.
        for cell in (
            await session.execute(select(Cell).where(Cell.column_id == column.id))
        ).scalars():
            await session.delete(cell)
    await session.commit()
    await session.refresh(column)
    return ColumnOut.model_validate(column)


@router.delete("/{review_id}/columns/{column_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_column(
    review_id: uuid.UUID, column_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> None:
    column = await _column(session, principal, review_id, column_id)
    await session.delete(column)
    await session.commit()


# --- runs -------------------------------------------------------------------


@router.post("/{review_id}/run", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
async def run_review(
    review_id: uuid.UUID, body: RunRequest, principal: CurrentPrincipal, session: DbSession
) -> RunOut:
    settings = get_settings()
    review = await ReviewRepository(session, principal.workspace_id).get_full(review_id)

    document_ids = [rd.document_id for rd in review.documents]
    if body.document_id is not None:
        if body.document_id not in document_ids:
            raise NotFoundError("document")
        document_ids = [body.document_id]
    columns = list(review.columns)
    if body.column_id is not None:
        columns = [c for c in columns if c.id == body.column_id]
        if not columns:
            raise NotFoundError("column")
    if not document_ids or not columns:
        raise ConflictError("nothing to run: the review needs at least one document and one column")

    targets = [[str(d), str(c.id)] for d in document_ids for c in columns]
    total = len(targets)
    mode = (
        RunMode(body.mode)
        if body.mode != "auto"
        else (RunMode.BATCH if total > settings.batch_threshold_cells else RunMode.INTERACTIVE)
    )
    run = ReviewRun(
        review_id=review.id,
        workspace_id=principal.workspace_id,
        mode=mode,
        status=RunStatus.QUEUED,
        total_cells=total,
        targets=targets,
        force=body.force,
    )
    session.add(run)

    # Show every targeted cell as pending immediately.
    existing = {
        (c.document_id, c.column_id): c
        for c in (
            await session.execute(
                select(Cell).where(
                    Cell.review_id == review.id,
                    Cell.document_id.in_(document_ids),
                    Cell.column_id.in_([c.id for c in columns]),
                )
            )
        ).scalars()
    }
    pending: list[Cell] = []
    for document_id in document_ids:
        for column in columns:
            cell = existing.get((document_id, column.id))
            if cell is None:
                cell = Cell(
                    review_id=review.id,
                    workspace_id=principal.workspace_id,
                    document_id=document_id,
                    column_id=column.id,
                )
                session.add(cell)
            cell.status = CellStatus.PENDING
            cell.error = None
            pending.append(cell)
    await session.commit()
    for cell in pending:
        await session.refresh(cell, attribute_names=["citations"])
        await publish_cell(cell)

    if mode is RunMode.BATCH:
        await enqueue("run_batch", str(run.id))
    else:
        for document_id in document_ids:
            for group in group_columns(columns, settings.columns_per_call):
                await enqueue(
                    "run_cells", str(run.id), str(document_id), [str(c.id) for c in group]
                )
    await session.refresh(run)
    return RunOut.model_validate(run)


@router.get("/{review_id}/runs/{run_id}", response_model=RunOut)
async def get_run(
    review_id: uuid.UUID, run_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> RunOut:
    await ReviewRepository(session, principal.workspace_id).get(review_id)
    run = (
        await session.execute(
            select(ReviewRun).where(ReviewRun.id == run_id, ReviewRun.review_id == review_id)
        )
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundError("run")
    return RunOut.model_validate(run)


@router.get("/{review_id}/stream")
async def stream_review(
    review_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> StreamingResponse:
    await ReviewRepository(session, principal.workspace_id).get(review_id)

    async def generate() -> AsyncIterator[bytes]:
        yield b"event: ready\ndata: {}\n\n"
        if not get_settings().queue_enabled:
            return
        async for event, payload in events.subscribe(review_id):
            if event == "heartbeat":
                yield b": keep-alive\n\n"
                continue
            yield f"event: {event}\ndata: {json.dumps(payload)}\n\n".encode()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- export -----------------------------------------------------------------


@router.get("/{review_id}/export")
async def export_review(
    review_id: uuid.UUID,
    principal: CurrentPrincipal,
    session: DbSession,
    format: Annotated[str, Query(pattern="^(csv|xlsx)$")] = "csv",
) -> Response:
    review = await ReviewRepository(session, principal.workspace_id).get_full(review_id)
    documents = {
        d.id: d
        for d in (
            await session.execute(
                select(Document).where(Document.id.in_([rd.document_id for rd in review.documents]))
            )
        ).scalars()
    }
    cells = (await session.execute(select(Cell).where(Cell.review_id == review.id))).scalars().all()
    by_doc: dict[uuid.UUID, dict[str, Cell]] = {}
    for cell in cells:
        by_doc.setdefault(cell.document_id, {})[str(cell.column_id)] = cell
    rows = [
        (documents[rd.document_id].filename, by_doc.get(rd.document_id, {}))
        for rd in review.documents
        if rd.document_id in documents
    ]
    headers, body = export.build_table(rows, list(review.columns))
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    safe = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in review.name).strip()
    if format == "xlsx":
        return Response(
            content=export.to_xlsx(headers, body),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{safe}-{stamp}.xlsx"'},
        )
    return Response(
        content=export.to_csv(headers, body),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{safe}-{stamp}.csv"'},
    )
