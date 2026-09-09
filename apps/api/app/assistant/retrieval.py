"""Hybrid retrieval across several documents, fused and reranked.

Lexical (``ts_rank_cd``) and vector (pgvector cosine) candidates are fused by
reciprocal rank, then reranked by lexical overlap with the question so that a
passage naming the defined term or clause number the user typed wins over a
merely thematic neighbour. Vector hits farther than
``assistant_vector_max_distance`` are not treated as relevant on their own:
without that guard "nothing relevant" could never happen, and refusing to
guess is a product requirement.
"""

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.ingestion.embeddings import Embedder
from app.llm.schema import Passage
from app.models.chunk import Chunk
from app.models.document import Document
from app.review.context import RRF_K, lexical_query

_WORD = re.compile(r"[a-z0-9]+")
_STOP = {
    "the",
    "a",
    "an",
    "of",
    "and",
    "or",
    "is",
    "are",
    "what",
    "which",
    "does",
    "do",
    "this",
    "that",
    "in",
    "to",
    "for",
    "any",
    "with",
    "be",
    "by",
    "on",
    "it",
    "its",
    "as",
    "at",
    "who",
    "how",
    "when",
    "there",
    "under",
    "agreement",
    "contract",
    "document",
    "documents",
    "clause",
    "please",
    "tell",
    "me",
    "about",
    "can",
    "you",
    "i",
    "we",
    "they",
    "he",
    "she",
    "from",
}


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    document: Document
    label: str
    score: float


def label_for(doc_index: int, chunk: Chunk) -> str:
    return f"d{doc_index}c{chunk.ordinal}"


def _keywords(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 2}


async def _lexical(
    session: AsyncSession, document_ids: list[uuid.UUID], question: str, limit: int
) -> list[uuid.UUID]:
    tsv = func.to_tsvector("english", Chunk.text)
    query = func.websearch_to_tsquery("english", lexical_query(question))
    stmt = (
        select(Chunk.id)
        .where(Chunk.document_id.in_(document_ids), tsv.op("@@")(query))
        .order_by(func.ts_rank_cd(tsv, query).desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def _vector(
    session: AsyncSession,
    document_ids: list[uuid.UUID],
    question: str,
    limit: int,
    embedder: Embedder | None,
    max_distance: float,
) -> list[uuid.UUID]:
    if embedder is None:
        return []
    [vector] = await embedder.embed([question])
    distance = Chunk.embedding.cosine_distance(vector)
    stmt = (
        select(Chunk.id)
        .where(
            Chunk.document_id.in_(document_ids),
            Chunk.embedding.is_not(None),
            distance <= max_distance,
        )
        .order_by(distance)
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def retrieve_across(
    session: AsyncSession,
    documents: list[Document],
    question: str,
    *,
    embedder: Embedder | None,
    k: int | None = None,
) -> list[Hit]:
    """Top-k passages across ``documents`` in document order, or [] when
    nothing is relevant. Neighbours of the strongest hits are included so a
    clause is not cut off from its heading."""
    settings = get_settings()
    k = k or settings.assistant_top_k
    if not documents:
        return []
    document_ids = [d.id for d in documents]
    doc_index = {d.id: i + 1 for i, d in enumerate(documents)}
    by_doc = {d.id: d for d in documents}

    lexical = await _lexical(session, document_ids, question, k * 2)
    vector = await _vector(
        session, document_ids, question, k * 2, embedder, settings.assistant_vector_max_distance
    )
    if not lexical and not vector:
        return []

    fused: dict[uuid.UUID, float] = {}
    for ranking in (lexical, vector):
        for rank, chunk_id in enumerate(ranking):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)

    rows = (await session.execute(select(Chunk).where(Chunk.id.in_(list(fused))))).scalars().all()
    chunks = {c.id: c for c in rows}

    # Rerank: fused score plus a lexical-overlap bonus, so the passage that
    # actually contains the user's words outranks a thematic cousin.
    keys = _keywords(question)
    scored: list[tuple[float, Chunk]] = []
    for chunk_id, base in fused.items():
        chunk = chunks.get(chunk_id)
        if chunk is None:
            continue
        overlap = len(keys & _keywords(chunk.text)) / (len(keys) or 1)
        scored.append((base + 0.05 * overlap, chunk))
    scored.sort(key=lambda pair: -pair[0])
    top = scored[:k]

    # Neighbours for the strongest few hits.
    wanted: dict[tuple[uuid.UUID, int], float] = {}
    for score, chunk in top:
        wanted[(chunk.document_id, chunk.ordinal)] = max(
            wanted.get((chunk.document_id, chunk.ordinal), 0.0), score
        )
    for score, chunk in top[:4]:
        for ordinal in (chunk.ordinal - 1, chunk.ordinal + 1):
            wanted.setdefault((chunk.document_id, ordinal), score * 0.5)

    neighbour_rows = (
        (
            await session.execute(
                select(Chunk).where(
                    Chunk.document_id.in_(document_ids),
                    Chunk.ordinal.in_(sorted({o for _, o in wanted})),
                )
            )
        )
        .scalars()
        .all()
    )
    for c in neighbour_rows:
        chunks.setdefault(c.id, c)

    hits: list[Hit] = []
    for chunk in chunks.values():
        key = (chunk.document_id, chunk.ordinal)
        if key not in wanted:
            continue
        document = by_doc[chunk.document_id]
        hits.append(
            Hit(
                chunk=chunk,
                document=document,
                label=label_for(doc_index[chunk.document_id], chunk),
                score=wanted[key],
            )
        )
    hits.sort(key=lambda h: (doc_index[h.document.id], h.chunk.ordinal))
    return hits


def passages_for(hits: list[Hit]) -> tuple[Passage, ...]:
    return tuple(
        Passage(
            label=h.label,
            section_path=f"document: {h.document.filename}"
            + (f" > {h.chunk.section_path}" if h.chunk.section_path else ""),
            text=h.chunk.text,
        )
        for h in hits
    )
