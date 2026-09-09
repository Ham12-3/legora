"""Tabular Review against the database with the fake model.

The queue is disabled in tests, so POST /run records the run and marks cells
pending; the tests then invoke the worker's executor directly, exactly as the
worker would, and read the grid back through the API.
"""

import uuid
from pathlib import Path

import httpx
import pytest

from app.config import get_settings
from app.db import SessionLocal
from app.ingestion import pipeline
from app.ingestion.embeddings import FakeEmbedder
from app.llm.fake import FakeLLMClient
from app.models.review import ReviewRun
from app.review import batch, executor
from app.review.context import build_context
from tests.conftest import Actor, MakeActor, create_document, create_matter

FIXTURES = Path(__file__).parent.parent / "fixtures"
PDF = "application/pdf"

QUESTIONS = [
    ("Governing law", "Which law governs this agreement?", "text", None),
    ("Liability cap", "What is the cap on each party's aggregate liability?", "money", None),
    ("Termination for convenience", "Can either party terminate for convenience?", "boolean", None),
    ("Initial term", "What is the initial term of the agreement?", "text", None),
    (
        "Jurisdiction",
        "Which courts have jurisdiction?",
        "enum",
        ["England and Wales", "New York", "Other"],
    ),
    ("Auto-renewal", "Does the agreement renew automatically?", "boolean", None),
    ("Non-compete", "Is there a non-compete restriction on either party?", "boolean", None),
]


def loader_for(name: str) -> pipeline.Loader:
    data = (FIXTURES / name).read_bytes()

    async def _load(_: str) -> bytes:
        return data

    return _load


async def ingest(document_id: uuid.UUID, fixture: str) -> None:
    async with SessionLocal() as session:
        await pipeline.run_all(
            session, document_id, loader=loader_for(fixture), embedder=FakeEmbedder(1536)
        )


async def make_review(
    client: httpx.AsyncClient, actor: Actor, fixtures: list[str]
) -> tuple[uuid.UUID, list[uuid.UUID], list[uuid.UUID]]:
    matter_id = await create_matter(client, actor)
    doc_ids = []
    for i, name in enumerate(fixtures):
        doc_id = await create_document(client, actor, matter_id, filename=name, sha256=f"{i:064x}")
        await ingest(doc_id, name)
        doc_ids.append(doc_id)

    r = await client.post(
        "/reviews",
        json={
            "matter_id": str(matter_id),
            "name": "Diligence",
            "document_ids": [str(d) for d in doc_ids],
        },
        headers=actor.headers,
    )
    assert r.status_code == 201, r.text
    review_id = uuid.UUID(r.json()["id"])

    col_ids = []
    for name, question, output_type, options in QUESTIONS:
        r = await client.post(
            f"/reviews/{review_id}/columns",
            json={
                "name": name,
                "question": question,
                "output_type": output_type,
                "enum_options": options,
            },
            headers=actor.headers,
        )
        assert r.status_code == 201, r.text
        col_ids.append(uuid.UUID(r.json()["id"]))
    return review_id, doc_ids, col_ids


async def execute_run(run_id: uuid.UUID, client_llm: FakeLLMClient) -> None:
    """What the worker does for an interactive run, in-process."""
    async with SessionLocal() as session:
        run = await session.get(ReviewRun, run_id)
        assert run is not None
        force = run.force
        by_doc: dict[uuid.UUID, list[uuid.UUID]] = {}
        for d, c in run.targets:
            by_doc.setdefault(uuid.UUID(d), []).append(uuid.UUID(c))
    for document_id, column_ids in by_doc.items():
        for group in executor.group_columns(column_ids):
            async with SessionLocal() as session:
                await executor.run_cells(
                    session,
                    review_id=(await _review_of(run_id)),
                    document_id=document_id,
                    column_ids=group,
                    force=force,
                    client=client_llm,
                    embedder=None,
                )


async def _review_of(run_id: uuid.UUID) -> uuid.UUID:
    async with SessionLocal() as session:
        run = await session.get(ReviewRun, run_id)
        assert run is not None
        return run.review_id


async def test_grid_fills_with_verified_cells(
    client: httpx.AsyncClient, make_actor: MakeActor
) -> None:
    alice = await make_actor("alice")
    review_id, doc_ids, col_ids = await make_review(client, alice, ["msa.pdf", "nda.pdf"])
    fake = FakeLLMClient()

    r = await client.post(f"/reviews/{review_id}/run", json={}, headers=alice.headers)
    assert r.status_code == 202, r.text
    run = r.json()
    assert run["mode"] == "interactive"
    assert run["total_cells"] == len(doc_ids) * len(col_ids)

    detail = (await client.get(f"/reviews/{review_id}", headers=alice.headers)).json()
    assert {c["status"] for c in detail["cells"]} == {"pending"}

    await execute_run(uuid.UUID(run["id"]), fake)

    # 7 columns per document -> 2 model calls per document (6 + 1).
    assert len(fake.calls) == 2 * len(doc_ids)
    assert max(len(c.questions) for c in fake.calls) == 6

    detail = (await client.get(f"/reviews/{review_id}", headers=alice.headers)).json()
    cells = detail["cells"]
    assert len(cells) == len(doc_ids) * len(col_ids)
    assert {c["status"] for c in cells} == {"done"}
    assert detail["demo_mode"] is True

    answered = [c for c in cells if not c["not_found"]]
    assert answered, "the fake should find at least some answers"
    for c in answered:
        assert c["verified"] is True, c
        assert c["citations"], c
        for cit in c["citations"]:
            assert cit["match_kind"] in {"exact", "relocated"}
            assert cit["page"] >= 1
            assert cit["char_end"] > cit["char_start"]
            assert cit["bboxes"], "PDF citations must carry boxes for the viewer"
    # The configured version, not a literal: bumping PROMPT_VERSION is a
    # routine change and should not fail a test about recording it.
    version = get_settings().prompt_version
    assert all(c["model"] == "fake" and c["prompt_version"] == version for c in cells)

    by_col = {c["column_id"]: c for c in cells if c["document_id"] == str(doc_ids[0])}
    boolean_cell = by_col[str(col_ids[2])]
    assert boolean_cell["value_json"] in (True, False, None)


async def test_fabricated_quotes_leave_the_cell_unverified(
    client: httpx.AsyncClient, make_actor: MakeActor
) -> None:
    alice = await make_actor("alice")
    review_id, _doc_ids, col_ids = await make_review(client, alice, ["msa.pdf"])
    liar = FakeLLMClient(fabricate=True)

    r = await client.post(
        f"/reviews/{review_id}/run", json={"column_id": str(col_ids[0])}, headers=alice.headers
    )
    await execute_run(uuid.UUID(r.json()["id"]), liar)

    detail = (await client.get(f"/reviews/{review_id}", headers=alice.headers)).json()
    [cell] = [c for c in detail["cells"] if c["column_id"] == str(col_ids[0])]
    assert cell["status"] == "done"
    assert cell["value_text"], "the answer is still shown..."
    assert cell["verified"] is False, "...but flagged, because no quote survived"
    assert cell["citations"] == [], "unverified quotes are dropped, never stored"


async def test_rerun_hits_the_cache(client: httpx.AsyncClient, make_actor: MakeActor) -> None:
    alice = await make_actor("alice")
    review_id, _doc_ids, _col_ids = await make_review(client, alice, ["msa.pdf"])
    fake = FakeLLMClient()

    r = await client.post(f"/reviews/{review_id}/run", json={}, headers=alice.headers)
    await execute_run(uuid.UUID(r.json()["id"]), fake)
    calls_after_first = len(fake.calls)
    assert calls_after_first > 0

    r = await client.post(f"/reviews/{review_id}/run", json={}, headers=alice.headers)
    await execute_run(uuid.UUID(r.json()["id"]), fake)
    assert len(fake.calls) == calls_after_first, "second run must be served from cache"

    detail = (await client.get(f"/reviews/{review_id}", headers=alice.headers)).json()
    assert all(c["from_cache"] for c in detail["cells"])
    assert all(c["status"] == "done" for c in detail["cells"])

    r = await client.post(f"/reviews/{review_id}/run", json={"force": True}, headers=alice.headers)
    await execute_run(uuid.UUID(r.json()["id"]), fake)
    assert len(fake.calls) > calls_after_first, "force bypasses the cache"


async def test_single_cell_rerun_scope(client: httpx.AsyncClient, make_actor: MakeActor) -> None:
    alice = await make_actor("alice")
    review_id, doc_ids, col_ids = await make_review(client, alice, ["msa.pdf", "nda.pdf"])
    r = await client.post(
        f"/reviews/{review_id}/run",
        json={"document_id": str(doc_ids[1]), "column_id": str(col_ids[0])},
        headers=alice.headers,
    )
    assert r.json()["total_cells"] == 1
    detail = (await client.get(f"/reviews/{review_id}", headers=alice.headers)).json()
    assert len(detail["cells"]) == 1


async def test_batch_mode_uses_the_same_verification_path(
    client: httpx.AsyncClient, make_actor: MakeActor
) -> None:
    alice = await make_actor("alice")
    review_id, _doc_ids, col_ids = await make_review(client, alice, ["msa.pdf"])
    fake = FakeLLMClient()

    r = await client.post(
        f"/reviews/{review_id}/run", json={"mode": "batch"}, headers=alice.headers
    )
    assert r.json()["mode"] == "batch"
    run_id = uuid.UUID(r.json()["id"])

    async with SessionLocal() as session:
        run = await session.get(ReviewRun, run_id)
        assert run is not None
        await batch.submit_run(session, run, client=fake, embedder=None)
        assert run.status.value == "submitted"
        assert run.provider_batch_id and run.provider_batch_id.startswith("fake-batch-")
        assert len(run.batch_plan) == 2  # 7 columns -> two requests
        done = await batch.poll_run(session, run, client=fake, embedder=None)
        assert done
        assert run.status.value == "done"
        assert run.done_cells == len(col_ids)

    detail = (await client.get(f"/reviews/{review_id}", headers=alice.headers)).json()
    assert {c["status"] for c in detail["cells"]} == {"done"}
    assert all(c["verified"] for c in detail["cells"] if not c["not_found"])


async def test_auto_mode_picks_batch_for_large_runs(
    client: httpx.AsyncClient, make_actor: MakeActor, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "batch_threshold_cells", 5)
    alice = await make_actor("alice")
    review_id, _, _ = await make_review(client, alice, ["msa.pdf"])
    r = await client.post(f"/reviews/{review_id}/run", json={}, headers=alice.headers)
    assert r.json()["mode"] == "batch"


async def test_router_uses_retrieval_above_threshold(
    client: httpx.AsyncClient, make_actor: MakeActor
) -> None:
    alice = await make_actor("alice")
    matter_id = await create_matter(client, alice)
    doc_id = await create_document(client, alice, matter_id, filename="msa.pdf")
    await ingest(doc_id, "msa.pdf")

    async with SessionLocal() as session:
        from app.models.document import Document

        document = await session.get(Document, doc_id)
        assert document is not None
        full = await build_context(session, document, ["indemnify"], embedder=None)
        assert full.mode == "full"
        assert len(full.passages) == len(full.chunks)

        # k=1 because the fixture has only a handful of chunks; the default k
        # would legitimately select all of them.
        narrow = await build_context(
            session,
            document,
            ["Which law governs this agreement?"],
            embedder=None,
            threshold=50,
            top_k=1,
        )
        assert narrow.mode == "retrieval"
        assert 0 < len(narrow.passages) < len(narrow.chunks)
        hit = " ".join(" ".join(p.text.split()) for p in narrow.passages)
        assert "governed by the laws of England and Wales" in hit
        assert narrow.outline, "the outline tells the model what it is not seeing"


async def test_export_marks_unverified_and_not_found(
    client: httpx.AsyncClient, make_actor: MakeActor
) -> None:
    alice = await make_actor("alice")
    review_id, _doc_ids, _col_ids = await make_review(client, alice, ["msa.pdf"])
    r = await client.post(f"/reviews/{review_id}/run", json={}, headers=alice.headers)
    await execute_run(uuid.UUID(r.json()["id"]), FakeLLMClient(fabricate=True))

    csv_resp = await client.get(f"/reviews/{review_id}/export?format=csv", headers=alice.headers)
    assert csv_resp.status_code == 200
    body = csv_resp.content.decode("utf-8-sig")
    header, row = body.strip().splitlines()[:2]
    assert header.startswith("Document,Governing law,")
    assert row.startswith("msa.pdf,")
    assert "[UNVERIFIED]" in row or "Not found" in row

    xlsx = await client.get(f"/reviews/{review_id}/export?format=xlsx", headers=alice.headers)
    assert xlsx.status_code == 200
    assert xlsx.content[:2] == b"PK"
    assert "attachment" in xlsx.headers["content-disposition"]


async def test_changing_a_question_clears_its_cells(
    client: httpx.AsyncClient, make_actor: MakeActor
) -> None:
    alice = await make_actor("alice")
    review_id, _doc_ids, col_ids = await make_review(client, alice, ["msa.pdf"])
    r = await client.post(f"/reviews/{review_id}/run", json={}, headers=alice.headers)
    await execute_run(uuid.UUID(r.json()["id"]), FakeLLMClient())

    r = await client.patch(
        f"/reviews/{review_id}/columns/{col_ids[0]}",
        json={"question": "What is the governing law and jurisdiction?"},
        headers=alice.headers,
    )
    assert r.status_code == 200
    detail = (await client.get(f"/reviews/{review_id}", headers=alice.headers)).json()
    assert not any(c["column_id"] == str(col_ids[0]) for c in detail["cells"])
    assert len(detail["cells"]) == len(col_ids) - 1


async def test_not_ready_document_fails_cells_clearly(
    client: httpx.AsyncClient, make_actor: MakeActor
) -> None:
    alice = await make_actor("alice")
    matter_id = await create_matter(client, alice)
    doc_id = await create_document(client, alice, matter_id, filename="pending.pdf")
    r = await client.post(
        "/reviews",
        json={"matter_id": str(matter_id), "name": "Early", "document_ids": [str(doc_id)]},
        headers=alice.headers,
    )
    review_id = uuid.UUID(r.json()["id"])
    col = await client.post(
        f"/reviews/{review_id}/columns",
        json={"name": "Law", "question": "Which law governs?", "output_type": "text"},
        headers=alice.headers,
    )
    run = await client.post(f"/reviews/{review_id}/run", json={}, headers=alice.headers)
    await execute_run(uuid.UUID(run.json()["id"]), FakeLLMClient())
    detail = (await client.get(f"/reviews/{review_id}", headers=alice.headers)).json()
    [cell] = detail["cells"]
    assert cell["status"] == "failed"
    assert "not ready" in cell["error"]
    assert cell["column_id"] == col.json()["id"]
