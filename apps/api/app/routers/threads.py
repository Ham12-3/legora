"""Assistant threads.

``POST /threads/{id}/messages`` is the one place outside the worker that calls
a model, and it does so as an explicitly streamed endpoint (CLAUDE.md rule 6):
the response is an SSE stream of status, answer deltas, and the final verified
message.
"""

import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.assistant.service import answer_stream
from app.auth.deps import CurrentPrincipal, DbSession
from app.config import get_settings
from app.errors import ConflictError, NotFoundError
from app.ingestion.embeddings import get_embedder
from app.llm.client import LLMClient, get_llm_client
from app.models.document import Document
from app.models.thread import Message, Thread, ThreadDocument
from app.repositories.base import WorkspaceScopedRepository
from app.repositories.documents import DocumentRepository
from app.repositories.matters import MatterRepository
from app.schemas.threads import (
    MessageCreate,
    MessageOut,
    ThreadCreate,
    ThreadDetail,
    ThreadDocumentOut,
    ThreadDocumentsUpdate,
    ThreadOut,
)

router = APIRouter(prefix="/threads", tags=["assistant"])

_llm: LLMClient | None = None


def llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = get_llm_client()
    return _llm


class ThreadRepository(WorkspaceScopedRepository[Thread]):
    model = Thread

    async def get_full(self, thread_id: uuid.UUID) -> Thread:
        stmt = (
            self.scoped()
            .where(Thread.id == thread_id)
            .options(selectinload(Thread.documents), selectinload(Thread.messages))
        )
        thread = (await self.session.execute(stmt)).scalar_one_or_none()
        if thread is None:
            raise NotFoundError("thread")
        return thread


def _out(thread: Thread) -> ThreadOut:
    return ThreadOut(
        id=thread.id,
        matter_id=thread.matter_id,
        title=thread.title,
        created_at=thread.created_at,
        document_count=len(thread.documents),
        message_count=len(thread.messages),
    )


@router.get("", response_model=list[ThreadOut])
async def list_threads(
    principal: CurrentPrincipal,
    session: DbSession,
    matter_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[ThreadOut]:
    repo = ThreadRepository(session, principal.workspace_id)
    stmt = repo.scoped().options(selectinload(Thread.documents), selectinload(Thread.messages))
    if matter_id is not None:
        stmt = stmt.where(Thread.matter_id == matter_id)
    rows = (await session.execute(stmt.order_by(Thread.created_at.desc()))).scalars().all()
    return [_out(t) for t in rows]


@router.post("", response_model=ThreadOut, status_code=status.HTTP_201_CREATED)
async def create_thread(
    body: ThreadCreate, principal: CurrentPrincipal, session: DbSession
) -> ThreadOut:
    await MatterRepository(session, principal.workspace_id).get(body.matter_id)
    docs = DocumentRepository(session, principal.workspace_id)
    documents = [await docs.get(d) for d in body.document_ids]
    for d in documents:
        if d.matter_id != body.matter_id:
            raise ConflictError(f"document {d.id} belongs to another matter")
    thread = Thread(
        workspace_id=principal.workspace_id,
        matter_id=body.matter_id,
        title=body.title or "New conversation",
        created_by=principal.user_id,
    )
    ThreadRepository(session, principal.workspace_id).add(thread)
    await session.flush()
    for d in documents:
        session.add(ThreadDocument(thread_id=thread.id, document_id=d.id))
    await session.commit()
    return _out(await ThreadRepository(session, principal.workspace_id).get_full(thread.id))


@router.get("/{thread_id}", response_model=ThreadDetail)
async def get_thread(
    thread_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> ThreadDetail:
    thread = await ThreadRepository(session, principal.workspace_id).get_full(thread_id)
    documents = {
        d.id: d
        for d in (
            await session.execute(
                DocumentRepository(session, principal.workspace_id)
                .scoped()
                .where(Document.id.in_([td.document_id for td in thread.documents]))
            )
        ).scalars()
    }
    return ThreadDetail(
        thread=_out(thread),
        documents=[
            ThreadDocumentOut(
                document_id=d.id, filename=d.filename, mime_type=d.mime_type, status=d.status
            )
            for td in thread.documents
            if (d := documents.get(td.document_id)) is not None
        ],
        messages=[MessageOut.model_validate(m) for m in thread.messages],
        demo_mode=any(m.model == "fake" for m in thread.messages),
    )


@router.patch("/{thread_id}/documents", response_model=ThreadDetail)
async def set_thread_documents(
    thread_id: uuid.UUID,
    body: ThreadDocumentsUpdate,
    principal: CurrentPrincipal,
    session: DbSession,
) -> ThreadDetail:
    thread = await ThreadRepository(session, principal.workspace_id).get_full(thread_id)
    docs = DocumentRepository(session, principal.workspace_id)
    documents = [await docs.get(d) for d in body.document_ids]
    for d in documents:
        if d.matter_id != thread.matter_id:
            raise ConflictError(f"document {d.id} belongs to another matter")
    for td in list(thread.documents):
        await session.delete(td)
    await session.flush()
    for d in documents:
        session.add(ThreadDocument(thread_id=thread.id, document_id=d.id))
    await session.commit()
    return await get_thread(thread_id, principal, session)


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> None:
    await ThreadRepository(session, principal.workspace_id).delete(thread_id)
    await session.commit()


@router.post("/{thread_id}/messages")
async def post_message(
    thread_id: uuid.UUID,
    body: MessageCreate,
    principal: CurrentPrincipal,
    session: DbSession,
) -> StreamingResponse:
    thread = await ThreadRepository(session, principal.workspace_id).get_full(thread_id)
    if not thread.messages and thread.title == "New conversation":
        thread.title = body.content.strip()[:80]
        await session.commit()

    settings = get_settings()

    async def generate() -> AsyncIterator[bytes]:
        async for event, payload in answer_stream(
            session,
            thread,
            body.content.strip(),
            client=llm(),
            embedder=get_embedder(settings),
            settings=settings,
        ):
            yield f"event: {event}\ndata: {json.dumps(payload)}\n\n".encode()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{thread_id}/messages", response_model=list[MessageOut])
async def list_messages(
    thread_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> list[MessageOut]:
    await ThreadRepository(session, principal.workspace_id).get(thread_id)
    rows = (
        (
            await session.execute(
                select(Message).where(Message.thread_id == thread_id).order_by(Message.created_at)
            )
        )
        .scalars()
        .all()
    )
    return [MessageOut.model_validate(m) for m in rows]
