"""Answer one question in a thread: retrieve, generate, verify, persist.

``answer_stream`` yields SSE-shaped events:

    status   {"stage": "retrieving" | "generating"}
    delta    {"text": "..."}            answer prose as it is written
    message  MessageOut                 the final, verified assistant message
    error    {"detail": "..."}

Refusal is the first branch, not an afterthought: when retrieval finds nothing
relevant the assistant says so and the model is never called.
"""

import logging
import re
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.prompt import load_assistant_prompt
from app.assistant.retrieval import Hit, passages_for, retrieve_across
from app.config import Settings, get_settings
from app.ingestion.embeddings import Embedder
from app.ingestion.pipeline import load_parsed
from app.ingestion.types import ParsedDocument
from app.llm.client import LLMClient
from app.llm.schema import ChatAnswer, ChatRequest, ChatTurn
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.models.thread import Message, MessageRole, Thread
from app.review.verify import verify_quote
from app.schemas.threads import MessageOut

log = logging.getLogger(__name__)

NOTHING_FOUND = (
    "I couldn't find anything in the selected documents that addresses this. "
    "I only answer from the documents in this conversation, so I won't guess. "
    "Try rephrasing with the terms the contract uses, or add the document you expect "
    "to contain the answer."
)


async def _thread_documents(session: AsyncSession, thread: Thread) -> list[Document]:
    ids = [td.document_id for td in thread.documents]
    if not ids:
        return []
    rows = (
        (
            await session.execute(
                select(Document).where(
                    Document.id.in_(ids), Document.status == DocumentStatus.READY
                )
            )
        )
        .scalars()
        .all()
    )
    order = {d: i for i, d in enumerate(ids)}
    return sorted(rows, key=lambda d: order[d.id])


async def _history(session: AsyncSession, thread: Thread, limit: int) -> tuple[ChatTurn, ...]:
    rows = (
        (
            await session.execute(
                select(Message)
                .where(Message.thread_id == thread.id)
                .order_by(Message.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return tuple(ChatTurn(role=m.role.value, content=m.content) for m in reversed(rows))


async def verify_citations(
    session: AsyncSession,
    answer: ChatAnswer,
    hits: list[Hit],
    *,
    fuzzy_threshold: float,
) -> tuple[list[dict[str, Any]], set[int]]:
    """Locate every quote in its document. Returns the verified citation
    records and the set of markers whose quotes could not be found."""
    by_label = {h.label: h for h in hits}
    parsed_cache: dict[uuid.UUID, tuple[ParsedDocument, list[Chunk]]] = {}
    verified: list[dict[str, Any]] = []
    dropped: set[int] = set()

    for citation in answer.citations:
        hit = by_label.get(citation.chunk_id)
        if hit is None:
            dropped.add(citation.marker)
            continue
        document_id = hit.document.id
        if document_id not in parsed_cache:
            parsed = await load_parsed(session, document_id)
            chunks = list(
                (
                    await session.execute(
                        select(Chunk)
                        .where(Chunk.document_id == document_id)
                        .order_by(Chunk.ordinal)
                    )
                ).scalars()
            )
            parsed_cache[document_id] = (parsed, chunks)
        parsed, chunks = parsed_cache[document_id]
        named = next((c for c in chunks if c.id == hit.chunk.id), None)
        span = verify_quote(
            citation.text, named, parsed=parsed, chunks=chunks, fuzzy_threshold=fuzzy_threshold
        )
        if span is None:
            dropped.add(citation.marker)
            continue
        verified.append(
            {
                "marker": citation.marker,
                "document_id": str(document_id),
                "filename": hit.document.filename,
                "chunk_id": str(span.chunk.id) if span.chunk is not None else None,
                "quoted_text": span.quoted_text,
                "page": span.page,
                "char_start": span.char_start,
                "char_end": span.char_end,
                "bboxes": span.bboxes,
                "match_kind": span.match_kind,
            }
        )
    return verified, dropped


def strip_markers(text: str, markers: set[int]) -> str:
    """Remove [n] markers whose citations were dropped, so the prose never
    points at a source that is not there."""
    for marker in markers:
        text = re.sub(rf"\s?\[{marker}\]", "", text)
    return text


async def answer_stream(
    session: AsyncSession,
    thread: Thread,
    question: str,
    *,
    client: LLMClient,
    embedder: Embedder | None,
    settings: Settings | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    settings = settings or get_settings()

    user_message = Message(
        thread_id=thread.id,
        workspace_id=thread.workspace_id,
        role=MessageRole.USER,
        content=question,
    )
    session.add(user_message)
    await session.commit()
    yield ("message", MessageOut.model_validate(user_message).model_dump(mode="json"))

    yield ("status", {"stage": "retrieving"})
    documents = await _thread_documents(session, thread)
    hits = await retrieve_across(session, documents, question, embedder=embedder)

    assistant = Message(
        thread_id=thread.id,
        workspace_id=thread.workspace_id,
        role=MessageRole.ASSISTANT,
        content="",
        prompt_version=settings.prompt_version,
    )

    if not hits:
        assistant.content = NOTHING_FOUND
        assistant.insufficient = True
        assistant.verified = True
        assistant.model = None
        session.add(assistant)
        await session.commit()
        yield ("message", MessageOut.model_validate(assistant).model_dump(mode="json"))
        return

    request = ChatRequest(
        model=settings.model_synth,
        system_prompt=load_assistant_prompt(settings.prompt_version),
        passages=passages_for(hits),
        history=await _history(session, thread, settings.assistant_history_messages),
        question=question,
        metadata={"thread_id": str(thread.id)},
    )

    yield ("status", {"stage": "generating"})
    result = None
    try:
        async for kind, payload in client.chat(request):
            if kind == "delta":
                yield ("delta", {"text": payload})
            else:
                result = payload
    except Exception as exc:
        log.exception("assistant model call failed")
        assistant.content = "The model call failed; nothing was answered."
        assistant.error = f"{type(exc).__name__}: {exc}"
        assistant.verified = False
        session.add(assistant)
        await session.commit()
        yield ("error", {"detail": assistant.error})
        yield ("message", MessageOut.model_validate(assistant).model_dump(mode="json"))
        return

    assert result is not None
    answer = result.answer
    citations, dropped = await verify_citations(
        session, answer, hits, fuzzy_threshold=settings.citation_fuzzy_threshold
    )
    assistant.content = strip_markers(answer.answer, dropped).strip()
    assistant.citations = citations
    assistant.insufficient = answer.insufficient
    # Verified means: every claim that has a marker has a real source. An
    # answer that cited nothing at all (and is not a refusal) is unverified.
    assistant.verified = answer.insufficient or (bool(citations) and not dropped)
    assistant.model = result.model
    session.add(assistant)
    await session.commit()
    yield ("message", MessageOut.model_validate(assistant).model_dump(mode="json"))
