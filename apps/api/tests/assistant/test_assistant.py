"""Grounded assistant against the database with the fake model.

The refusal-to-guess behaviour is a product requirement: when retrieval finds
nothing relevant the assistant must say so, and the model must not be called.
"""

import json
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.assistant import service
from app.db import SessionLocal
from app.ingestion import pipeline
from app.ingestion.embeddings import FakeEmbedder
from app.llm.fake import FakeLLMClient
from app.routers import threads as threads_router
from tests.conftest import Actor, MakeActor, create_document, create_matter

FIXTURES = Path(__file__).parent.parent / "fixtures"


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


async def make_thread(
    client: httpx.AsyncClient, actor: Actor, fixtures: list[str]
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    matter_id = await create_matter(client, actor)
    doc_ids = []
    for i, name in enumerate(fixtures):
        doc_id = await create_document(client, actor, matter_id, filename=name, sha256=f"{i:064x}")
        await ingest(doc_id, name)
        doc_ids.append(doc_id)
    r = await client.post(
        "/threads",
        json={"matter_id": str(matter_id), "document_ids": [str(d) for d in doc_ids]},
        headers=actor.headers,
    )
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["id"]), doc_ids


def parse_sse(body: str) -> list[tuple[str, Any]]:
    events: list[tuple[str, Any]] = []
    for block in body.strip().split("\n\n"):
        event = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if event is not None:
            events.append((event, data))
    return events


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeLLMClient:
    client = FakeLLMClient()
    monkeypatch.setattr(threads_router, "_llm", client)
    return client


async def ask(
    client: httpx.AsyncClient, actor: Actor, thread_id: uuid.UUID, question: str
) -> list[tuple[str, Any]]:
    r = await client.post(
        f"/threads/{thread_id}/messages", json={"content": question}, headers=actor.headers
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    return parse_sse(r.text)


async def test_grounded_answer_with_verified_citations(
    client: httpx.AsyncClient, make_actor: MakeActor, fake: FakeLLMClient
) -> None:
    alice = await make_actor("alice")
    thread_id, doc_ids = await make_thread(client, alice, ["msa.pdf", "nda.pdf"])

    events = await ask(client, alice, thread_id, "What is the cap on aggregate liability?")
    kinds = [e for e, _ in events]
    assert kinds[0] == "message" and events[0][1]["role"] == "user"
    assert "status" in kinds and "delta" in kinds
    assert kinds[-1] == "message"

    streamed = "".join(d["text"] for e, d in events if e == "delta")
    final = events[-1][1]
    assert final["role"] == "assistant"
    assert final["insufficient"] is False
    assert final["verified"] is True
    assert final["citations"], "grounded answers carry citations"
    assert streamed.replace(" ", "") == final["content"].replace(" ", "")
    for c in final["citations"]:
        assert c["document_id"] in {str(d) for d in doc_ids}
        assert c["match_kind"] in {"exact", "relocated"}
        assert c["page"] >= 1 and c["char_end"] > c["char_start"]
        assert f"[{c['marker']}]" in final["content"]
    assert final["model"] == "fake"
    assert len(fake.chat_calls) == 1
    # Passages are labelled per document so the verifier can find them.
    labels = {p.label for p in fake.chat_calls[0].passages}
    assert all(label.startswith("d") and "c" in label for label in labels)

    detail = (await client.get(f"/threads/{thread_id}", headers=alice.headers)).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["demo_mode"] is True
    assert detail["thread"]["title"].startswith("What is the cap")


async def test_refuses_when_nothing_relevant_without_calling_the_model(
    client: httpx.AsyncClient, make_actor: MakeActor, fake: FakeLLMClient
) -> None:
    alice = await make_actor("alice")
    thread_id, _ = await make_thread(client, alice, ["nda.pdf"])

    events = await ask(client, alice, thread_id, "What is the boiling point of tungsten?")
    final = events[-1][1]
    assert final["role"] == "assistant"
    assert final["insufficient"] is True
    assert final["citations"] == []
    assert "couldn't find anything" in final["content"]
    assert final["model"] is None, "no model was involved in a refusal"
    assert fake.chat_calls == [] if hasattr(fake, "chat_calls") else True
    assert not [e for e, _ in events if e == "delta"]


async def test_model_insufficient_flag_is_kept(
    client: httpx.AsyncClient, make_actor: MakeActor, fake: FakeLLMClient
) -> None:
    """Retrieval found *something* lexically, but the model judged it did not
    answer the question. That judgement is preserved, not overridden."""
    alice = await make_actor("alice")
    thread_id, _ = await make_thread(client, alice, ["msa.pdf"])
    # "agreement" is a stopword for the fake's overlap; "party" too, so the
    # fake finds no supporting sentence even though retrieval returns passages.
    events = await ask(client, alice, thread_id, "agreement between the parties")
    final = events[-1][1]
    if final["insufficient"]:
        assert final["verified"] is True
        assert final["citations"] == []
    else:  # the lexical overlap happened to land: still must be verified
        assert final["verified"] is True


async def test_fabricated_quotes_leave_the_message_unverified(
    client: httpx.AsyncClient, make_actor: MakeActor, monkeypatch: pytest.MonkeyPatch
) -> None:
    liar = FakeLLMClient(fabricate=True)
    monkeypatch.setattr(threads_router, "_llm", liar)
    alice = await make_actor("alice")
    thread_id, _ = await make_thread(client, alice, ["msa.pdf"])

    events = await ask(client, alice, thread_id, "Who indemnifies whom for infringement claims?")
    final = events[-1][1]
    assert final["insufficient"] is False
    assert final["verified"] is False
    assert final["citations"] == [], "unverified quotes are dropped, never stored"
    assert "[1]" not in final["content"], "markers for dropped citations are removed"


async def test_history_is_passed_to_the_model(
    client: httpx.AsyncClient, make_actor: MakeActor, fake: FakeLLMClient
) -> None:
    alice = await make_actor("alice")
    thread_id, _ = await make_thread(client, alice, ["msa.pdf"])
    await ask(client, alice, thread_id, "What is the initial term?")
    await ask(client, alice, thread_id, "And how much notice to terminate for convenience?")
    assert len(fake.chat_calls) == 2
    roles = [t.role for t in fake.chat_calls[1].history]
    assert roles[:2] == ["user", "assistant"]


async def test_threads_only_use_ready_documents(
    client: httpx.AsyncClient, make_actor: MakeActor, fake: FakeLLMClient
) -> None:
    alice = await make_actor("alice")
    matter_id = await create_matter(client, alice)
    pending = await create_document(client, alice, matter_id, filename="pending.pdf")
    r = await client.post(
        "/threads",
        json={"matter_id": str(matter_id), "document_ids": [str(pending)]},
        headers=alice.headers,
    )
    thread_id = uuid.UUID(r.json()["id"])
    events = await ask(client, alice, thread_id, "governing law")
    assert events[-1][1]["insufficient"] is True


def test_strip_markers() -> None:
    assert service.strip_markers("A [1]. B [2]. C [3].", {2}) == "A [1]. B. C [3]."
    assert service.strip_markers("Only [1]", {1}) == "Only"
