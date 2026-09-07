"""Context routing: what part of the document does the model see?

Short document: all of it. Retrieval can only lose information. Long
document: hybrid retrieval (vector + lexical, fused by reciprocal rank) for
each question, top-k plus neighbours, plus a structural outline of the whole
document so the model knows what it is *not* seeing. The threshold is an
explicit token count in config, set by measurement — not by what the context
window allows (CLAUDE.md, section 3.6).
"""

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.ingestion.embeddings import Embedder
from app.ingestion.pipeline import load_parsed
from app.ingestion.types import ParsedDocument, estimate_tokens
from app.llm.schema import Passage
from app.models.chunk import Chunk
from app.models.document import Document

Mode = Literal["full", "retrieval"]
RRF_K = 60


@dataclass
class DocumentContext:
    document: Document
    parsed: ParsedDocument
    chunks: list[Chunk]  # every chunk, in order
    mode: Mode
    passages: tuple[Passage, ...]
    outline: tuple[str, ...]
    by_label: dict[str, Chunk]


def label_for(chunk: Chunk) -> str:
    return f"c{chunk.ordinal}"


def route(parsed: ParsedDocument, threshold: int | None = None) -> Mode:
    limit = threshold if threshold is not None else get_settings().full_context_token_threshold
    return "full" if estimate_tokens(parsed.text) <= limit else "retrieval"


def outline_of(chunks: list[Chunk], limit: int = 80) -> tuple[str, ...]:
    seen: list[str] = []
    for chunk in chunks:
        path = chunk.section_path
        if path and path not in seen:
            seen.append(path)
        if len(seen) >= limit:
            break
    return tuple(seen)


async def load_chunks(session: AsyncSession, document_id: uuid.UUID) -> list[Chunk]:
    rows = await session.execute(
        select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.ordinal)
    )
    return list(rows.scalars().all())


async def _lexical(
    session: AsyncSession, document_id: uuid.UUID, question: str, k: int
) -> list[uuid.UUID]:
    tsv = func.to_tsvector("english", Chunk.text)
    query = func.plainto_tsquery("english", question)
    stmt = (
        select(Chunk.id)
        .where(Chunk.document_id == document_id, tsv.op("@@")(query))
        .order_by(func.ts_rank_cd(tsv, query).desc())
        .limit(k)
    )
    return list((await session.execute(stmt)).scalars().all())


async def _vector(
    session: AsyncSession,
    document_id: uuid.UUID,
    question: str,
    k: int,
    embedder: Embedder | None,
) -> list[uuid.UUID]:
    if embedder is None:
        return []
    [vector] = await embedder.embed([question])
    stmt = (
        select(Chunk.id)
        .where(Chunk.document_id == document_id, Chunk.embedding.is_not(None))
        .order_by(Chunk.embedding.cosine_distance(vector))
        .limit(k)
    )
    return list((await session.execute(stmt)).scalars().all())


def rrf(*rankings: list[uuid.UUID]) -> list[uuid.UUID]:
    scores: dict[uuid.UUID, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)
    return sorted(scores, key=lambda cid: -scores[cid])


async def retrieve(
    session: AsyncSession,
    chunks: list[Chunk],
    question: str,
    *,
    k: int,
    embedder: Embedder | None,
) -> list[Chunk]:
    """Top-k fused hits plus their immediate neighbours, in document order."""
    if not chunks:
        return []
    document_id = chunks[0].document_id
    lexical = await _lexical(session, document_id, question, k)
    vector = await _vector(session, document_id, question, k, embedder)
    fused = rrf(lexical, vector)[:k]

    by_id = {c.id: c for c in chunks}
    by_ordinal = {c.ordinal: c for c in chunks}
    picked: set[int] = set()
    for chunk_id in fused:
        chunk = by_id.get(chunk_id)
        if chunk is None:
            continue
        for ordinal in (chunk.ordinal - 1, chunk.ordinal, chunk.ordinal + 1):
            if ordinal in by_ordinal:
                picked.add(ordinal)
    return [by_ordinal[o] for o in sorted(picked)]


async def build_context(
    session: AsyncSession,
    document: Document,
    questions: list[str],
    *,
    embedder: Embedder | None,
    threshold: int | None = None,
    top_k: int | None = None,
) -> DocumentContext:
    settings = get_settings()
    parsed = await load_parsed(session, document.id)
    chunks = await load_chunks(session, document.id)
    mode = route(parsed, threshold)

    if mode == "full":
        selected = chunks
    else:
        union: dict[int, Chunk] = {}
        for question in questions:
            for chunk in await retrieve(
                session, chunks, question, k=top_k or settings.retrieval_top_k, embedder=embedder
            ):
                union[chunk.ordinal] = chunk
        selected = [union[o] for o in sorted(union)]
        if not selected:  # nothing matched lexically and no vectors: show the opening
            selected = chunks[: min(len(chunks), 3)]

    passages = tuple(
        Passage(label=label_for(c), section_path=c.section_path, text=c.text) for c in selected
    )
    return DocumentContext(
        document=document,
        parsed=parsed,
        chunks=chunks,
        mode=mode,
        passages=passages,
        outline=outline_of(chunks),
        by_label={label_for(c): c for c in chunks},
    )
