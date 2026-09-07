"""The three ingestion stages, each a pure function of the database state.

    parse:  bytes in storage      -> document_pages rows, status "chunking"
    chunk:  document_pages rows   -> chunks rows,         status "embedding"
    embed:  chunks rows           -> chunks.embedding,    status "ready"

Every stage reads what it needs from the database and can therefore be
retried on its own. ``run_all`` is the in-process composition used by tests
and tooling; the worker runs them as separate jobs.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import storage
from app.config import get_settings
from app.ingestion.chunker import chunk_document
from app.ingestion.docx import parse_docx
from app.ingestion.embeddings import Embedder, get_embedder
from app.ingestion.pdf import parse_pdf
from app.ingestion.types import Page, ParsedDocument, Word, assemble_text
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.models.document_page import DocumentPage

log = logging.getLogger(__name__)

Loader = Callable[[str], Awaitable[bytes]]

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class IngestionError(Exception):
    """A permanent failure for this document: do not retry."""


async def storage_loader(storage_key: str) -> bytes:
    def _get() -> bytes:
        response = storage.internal_client().get_object(
            Bucket=get_settings().s3_bucket, Key=storage_key
        )
        return response["Body"].read()

    return await asyncio.to_thread(_get)


async def _load(session: AsyncSession, document_id: uuid.UUID) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise IngestionError(f"document {document_id} no longer exists")
    return document


async def _set_status(session: AsyncSession, document: Document, status: DocumentStatus) -> None:
    document.status = status
    document.error = None
    await session.commit()


def _parse(mime_type: str, data: bytes) -> ParsedDocument:
    if mime_type == "application/pdf":
        parser = parse_pdf
    elif mime_type == DOCX_MIME:
        parser = parse_docx
    else:
        raise IngestionError(f"unsupported mime type {mime_type}")
    try:
        return parser(data)
    except Exception as exc:
        # A file the parser cannot open will not open on the next try either;
        # retrying only delays the failure the user needs to see.
        raise IngestionError(f"file could not be parsed: {exc}") from exc


# --- stage 1 -----------------------------------------------------------------


async def run_parse(session: AsyncSession, document_id: uuid.UUID, loader: Loader) -> None:
    document = await _load(session, document_id)
    await _set_status(session, document, DocumentStatus.PARSING)

    data = await loader(document.storage_key)
    parsed = await asyncio.to_thread(_parse, document.mime_type, data)
    if not parsed.text.strip():
        raise IngestionError(
            "no extractable text" + (" (scanned; OCR unavailable)" if parsed.is_ocr else "")
        )

    # Idempotent: a retry replaces whatever an earlier attempt wrote.
    await session.execute(delete(Chunk).where(Chunk.document_id == document.id))
    await session.execute(delete(DocumentPage).where(DocumentPage.document_id == document.id))
    for page in parsed.pages:
        session.add(
            DocumentPage(
                document_id=document.id,
                workspace_id=document.workspace_id,
                page_number=page.number,
                text=page.text,
                char_offset=page.char_offset,
                width=page.width,
                height=page.height,
                words=[w.as_row() for w in page.words],
                is_ocr=page.is_ocr,
            )
        )
    document.page_count = len(parsed.pages)
    document.is_ocr = parsed.is_ocr
    await _set_status(session, document, DocumentStatus.CHUNKING)


# --- stage 2 -----------------------------------------------------------------


def _page_from_row(row: DocumentPage) -> Page:
    words = [Word(int(w[0]), int(w[1]), w[2], w[3], w[4], w[5]) for w in row.words]
    return Page(
        number=row.page_number,
        text=row.text,
        width=row.width,
        height=row.height,
        words=words,
        is_ocr=row.is_ocr,
        char_offset=row.char_offset,
    )


async def load_parsed(session: AsyncSession, document_id: uuid.UUID) -> ParsedDocument:
    """Rebuild the parser's output from document_pages. Used by chunking and by
    the citation verifier later; both must see exactly the same text."""
    rows = (
        (
            await session.execute(
                select(DocumentPage)
                .where(DocumentPage.document_id == document_id)
                .order_by(DocumentPage.page_number)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise IngestionError("no parsed pages; run parse first")
    pages = [_page_from_row(r) for r in rows]
    text = assemble_text(pages)
    # assemble_text recomputes offsets; they must agree with what parse stored.
    for row, page in zip(rows, pages, strict=True):
        if row.char_offset != page.char_offset:
            raise IngestionError(
                f"page {row.page_number} offset drift: "
                f"stored {row.char_offset}, rebuilt {page.char_offset}"
            )
    return ParsedDocument(pages=pages, text=text, is_ocr=any(p.is_ocr for p in pages))


async def run_chunk(session: AsyncSession, document_id: uuid.UUID) -> None:
    settings = get_settings()
    document = await _load(session, document_id)
    await _set_status(session, document, DocumentStatus.CHUNKING)

    parsed = await load_parsed(session, document.id)
    drafts = chunk_document(
        parsed,
        target_tokens=settings.chunk_target_tokens,
        max_tokens=settings.chunk_max_tokens,
    )
    if not drafts:
        raise IngestionError("chunker produced no chunks")

    for draft in drafts:
        if parsed.text[draft.char_start : draft.char_end] != draft.text:
            raise IngestionError(f"chunk {draft.ordinal} failed the offset round-trip")

    await session.execute(delete(Chunk).where(Chunk.document_id == document.id))
    for draft in drafts:
        session.add(
            Chunk(
                document_id=document.id,
                workspace_id=document.workspace_id,
                ordinal=draft.ordinal,
                text=draft.text,
                section_path=draft.section_path,
                page_start=draft.page_start,
                page_end=draft.page_end,
                char_start=draft.char_start,
                char_end=draft.char_end,
                token_count=draft.token_count,
                bboxes=draft.bboxes,
            )
        )
    await _set_status(session, document, DocumentStatus.EMBEDDING)


# --- stage 3 -----------------------------------------------------------------


def embedding_input(chunk: Chunk) -> str:
    """What gets embedded. The section path is context, not chunk text."""
    return f"{chunk.section_path}\n{chunk.text}" if chunk.section_path else chunk.text


async def run_embed(
    session: AsyncSession, document_id: uuid.UUID, embedder: Embedder | None
) -> None:
    settings = get_settings()
    document = await _load(session, document_id)
    await _set_status(session, document, DocumentStatus.EMBEDDING)

    if embedder is None:
        log.warning("document %s: embeddings skipped (provider disabled)", document.id)
        await _set_status(session, document, DocumentStatus.READY)
        return

    chunks = (
        (
            await session.execute(
                select(Chunk)
                .where(Chunk.document_id == document.id, Chunk.embedding.is_(None))
                .order_by(Chunk.ordinal)
            )
        )
        .scalars()
        .all()
    )

    batch = settings.embed_batch_size
    for i in range(0, len(chunks), batch):
        group = chunks[i : i + batch]
        vectors = await embedder.embed([embedding_input(c) for c in group])
        if len(vectors) != len(group):
            raise RuntimeError("embedder returned a different number of vectors than inputs")
        for chunk, vector in zip(group, vectors, strict=True):
            if len(vector) != settings.embed_dim:
                raise RuntimeError(
                    f"embedding has {len(vector)} dims, column is {settings.embed_dim}"
                )
            chunk.embedding = vector
        # Commit per batch so a mid-run failure resumes where it stopped.
        await session.commit()

    await _set_status(session, document, DocumentStatus.READY)


# --- composition -------------------------------------------------------------


async def run_all(
    session: AsyncSession,
    document_id: uuid.UUID,
    *,
    loader: Loader | None = None,
    embedder: Embedder | Literal["auto"] | None = "auto",
) -> None:
    """Run every stage in-process. Tests and the CLI use this; the worker
    chains the stages as separate jobs."""
    await run_parse(session, document_id, loader or storage_loader)
    await run_chunk(session, document_id)
    resolved = get_embedder() if embedder == "auto" else embedder
    await run_embed(session, document_id, resolved)


async def mark_failed(session: AsyncSession, document_id: uuid.UUID, error: str) -> None:
    document = await session.get(Document, document_id)
    if document is None:
        return
    document.status = DocumentStatus.FAILED
    document.error = error[:2000]
    await session.commit()
