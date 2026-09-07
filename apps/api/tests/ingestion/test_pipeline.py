"""The three stages against the database, with storage and embeddings faked."""

import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.ingestion import pipeline
from app.ingestion.embeddings import FakeEmbedder
from app.ingestion.types import PAGE_SEPARATOR
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.models.document_page import DocumentPage
from tests.conftest import MakeActor, create_document, create_matter

FIXTURES = Path(__file__).parent.parent / "fixtures"


def loader_for(name: str) -> pipeline.Loader:
    data = (FIXTURES / name).read_bytes()

    async def _load(_: str) -> bytes:
        return data

    return _load


async def ingest(document_id: uuid.UUID, fixture: str, embedder: FakeEmbedder | None) -> None:
    async with SessionLocal() as session:
        await pipeline.run_all(session, document_id, loader=loader_for(fixture), embedder=embedder)


async def test_full_pipeline_reaches_ready(
    client: httpx.AsyncClient, make_actor: MakeActor
) -> None:
    alice = await make_actor("alice")
    matter_id = await create_matter(client, alice)
    doc_id = await create_document(client, alice, matter_id, filename="msa.pdf")
    embedder = FakeEmbedder(1536)

    await ingest(doc_id, "msa.pdf", embedder)

    async with SessionLocal() as session:
        document = await session.get(Document, doc_id)
        assert document is not None
        assert document.status is DocumentStatus.READY
        assert document.error is None
        assert document.page_count and document.page_count >= 2
        assert document.is_ocr is False

        pages = (
            (
                await session.execute(
                    select(DocumentPage)
                    .where(DocumentPage.document_id == doc_id)
                    .order_by(DocumentPage.page_number)
                )
            )
            .scalars()
            .all()
        )
        chunks = (
            (
                await session.execute(
                    select(Chunk).where(Chunk.document_id == doc_id).order_by(Chunk.ordinal)
                )
            )
            .scalars()
            .all()
        )

    assert len(pages) == document.page_count
    assert all(p.workspace_id == alice.workspace_id for p in pages)
    assert all(c.workspace_id == alice.workspace_id for c in chunks)

    # The invariant, this time against what is actually in the database.
    document_text = PAGE_SEPARATOR.join(p.text for p in pages)
    for chunk in chunks:
        assert document_text[chunk.char_start : chunk.char_end] == chunk.text

    assert all(c.embedding is not None and len(c.embedding) == 1536 for c in chunks)
    assert embedder.batches and max(embedder.batches) <= 96
    assert sum(embedder.batches) == len(chunks)

    # The response the UI sees.
    r = await client.get(f"/documents/{doc_id}", headers=alice.headers)
    assert r.json()["status"] == "ready"
    assert r.json()["page_count"] == document.page_count

    listed = await client.get(f"/documents/{doc_id}/chunks", headers=alice.headers)
    assert listed.status_code == 200
    assert [c["ordinal"] for c in listed.json()] == list(range(len(chunks)))
    assert listed.json()[0]["section_path"] is not None


async def test_stages_are_independently_rerunnable(
    client: httpx.AsyncClient, make_actor: MakeActor
) -> None:
    alice = await make_actor("alice")
    matter_id = await create_matter(client, alice)
    doc_id = await create_document(client, alice, matter_id, filename="nda.pdf")

    async with SessionLocal() as session:
        await pipeline.run_parse(session, doc_id, loader_for("nda.pdf"))
        await pipeline.run_chunk(session, doc_id)
        first = (
            (await session.execute(select(Chunk.id).where(Chunk.document_id == doc_id)))
            .scalars()
            .all()
        )

        # Re-running chunking replaces rather than duplicates.
        await pipeline.run_chunk(session, doc_id)
        second = (
            (await session.execute(select(Chunk.id).where(Chunk.document_id == doc_id)))
            .scalars()
            .all()
        )
        assert len(first) == len(second)
        assert set(first).isdisjoint(second)

        # Embedding with the provider disabled still reaches ready.
        await pipeline.run_embed(session, doc_id, None)
        document = await session.get(Document, doc_id)
        assert document is not None and document.status is DocumentStatus.READY


async def test_docx_goes_through_the_same_pipeline(
    client: httpx.AsyncClient, make_actor: MakeActor
) -> None:
    alice = await make_actor("alice")
    matter_id = await create_matter(client, alice)
    docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    doc_id = await create_document(
        client, alice, matter_id, filename="msa.docx", sha256="e" * 64, mime_type=docx_mime
    )
    await ingest(doc_id, "msa.docx", FakeEmbedder(1536))
    async with SessionLocal() as session:
        document = await session.get(Document, doc_id)
        assert document is not None
        assert document.status is DocumentStatus.READY
        assert document.page_count == 1


async def test_scanned_without_ocr_fails_with_a_clear_reason(
    client: httpx.AsyncClient, make_actor: MakeActor
) -> None:
    alice = await make_actor("alice")
    matter_id = await create_matter(client, alice)
    doc_id = await create_document(client, alice, matter_id, filename="scan.pdf", sha256="f" * 64)

    async with SessionLocal() as session:
        with pytest.raises(pipeline.IngestionError, match="scanned"):
            await pipeline.run_parse(session, doc_id, loader_for("scanned_nda.pdf"))
        await pipeline.mark_failed(
            session, doc_id, "no extractable text (scanned; OCR unavailable)"
        )

    r = await client.get(f"/documents/{doc_id}", headers=alice.headers)
    assert r.json()["status"] == "failed"
    assert "scanned" in r.json()["error"]

    # Reingest resets the row so the worker can pick it up again.
    again = await client.post(f"/documents/{doc_id}/reingest", headers=alice.headers)
    assert again.status_code == 200
    assert again.json()["status"] == "uploaded"
    assert again.json()["error"] is None


async def test_corrupt_file_is_a_permanent_failure(
    client: httpx.AsyncClient, make_actor: MakeActor
) -> None:
    """A file the parser cannot open must not be retried as if it were transient."""
    alice = await make_actor("alice")
    matter_id = await create_matter(client, alice)
    doc_id = await create_document(client, alice, matter_id, filename="junk.pdf", sha256="1" * 64)

    async def junk(_: str) -> bytes:
        return b"%PDF-1.4 this is not a pdf\n%%EOF\n"

    async with SessionLocal() as session:
        with pytest.raises(pipeline.IngestionError, match="could not be parsed"):
            await pipeline.run_parse(session, doc_id, junk)
