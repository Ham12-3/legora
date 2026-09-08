"""Rule 1 in CLAUDE.md, as a test.

A user in workspace B, holding real ids from workspace A, gets 404 from every
endpoint that addresses a matter or a document. Not 403: the API never confirms
that a foreign entity exists.

``test_every_entity_route_is_covered`` walks the FastAPI router and fails if a
new ``{matter_id}`` or ``{document_id}`` route lands without an entry in
``ENTITY_ROUTES`` below. Adding an endpoint means adding it here.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass

import httpx
import pytest
from fastapi.routing import APIRoute

from app.main import app
from tests.conftest import PDF, Actor, MakeActor, create_document, create_matter


@dataclass(frozen=True)
class Ids:
    matter_id: uuid.UUID
    document_id: uuid.UUID
    review_id: uuid.UUID
    column_id: uuid.UUID
    run_id: uuid.UUID
    thread_id: uuid.UUID


@dataclass(frozen=True)
class EntityRoute:
    method: str
    template: str
    body: Callable[[Ids], dict[str, object]] | None = None

    def path(self, ids: Ids) -> str:
        return self.template.format(
            matter_id=ids.matter_id,
            document_id=ids.document_id,
            review_id=ids.review_id,
            column_id=ids.column_id,
            run_id=ids.run_id,
            thread_id=ids.thread_id,
        )


def _presign_body(ids: Ids) -> dict[str, object]:
    return {"filename": "x.pdf", "mime_type": PDF, "size_bytes": 10, "sha256": "b" * 64}


def _add_docs_body(ids: Ids) -> dict[str, object]:
    return {"document_ids": [str(ids.document_id)]}


COLUMN_BODY: dict[str, object] = {
    "name": "Law",
    "question": "Which law governs?",
    "output_type": "text",
}


def _register_body(ids: Ids) -> dict[str, object]:
    return {
        "document_id": str(uuid.uuid4()),
        "storage_key": "irrelevant",
        "filename": "x.pdf",
        "mime_type": PDF,
        "size_bytes": 10,
        "sha256": "b" * 64,
    }


ENTITY_ROUTES: list[EntityRoute] = [
    EntityRoute("GET", "/matters/{matter_id}"),
    EntityRoute("DELETE", "/matters/{matter_id}"),
    EntityRoute("GET", "/matters/{matter_id}/documents"),
    EntityRoute("POST", "/matters/{matter_id}/documents/presign", _presign_body),
    EntityRoute("POST", "/matters/{matter_id}/documents", _register_body),
    EntityRoute("GET", "/documents/{document_id}"),
    EntityRoute("GET", "/documents/{document_id}/download"),
    EntityRoute("GET", "/documents/{document_id}/chunks"),
    EntityRoute("POST", "/documents/{document_id}/reingest"),
    EntityRoute("DELETE", "/documents/{document_id}"),
    EntityRoute("GET", "/reviews/{review_id}"),
    EntityRoute("DELETE", "/reviews/{review_id}"),
    EntityRoute("POST", "/reviews/{review_id}/documents", _add_docs_body),
    EntityRoute("DELETE", "/reviews/{review_id}/documents/{document_id}"),
    EntityRoute("POST", "/reviews/{review_id}/columns", lambda ids: dict(COLUMN_BODY)),
    EntityRoute("PATCH", "/reviews/{review_id}/columns/{column_id}", lambda ids: {"name": "X"}),
    EntityRoute("DELETE", "/reviews/{review_id}/columns/{column_id}"),
    EntityRoute("POST", "/reviews/{review_id}/run", lambda ids: {}),
    EntityRoute("GET", "/reviews/{review_id}/runs/{run_id}"),
    EntityRoute("GET", "/reviews/{review_id}/stream"),
    EntityRoute("GET", "/reviews/{review_id}/export"),
    EntityRoute("GET", "/threads/{thread_id}"),
    EntityRoute("DELETE", "/threads/{thread_id}"),
    EntityRoute("PATCH", "/threads/{thread_id}/documents", _add_docs_body),
    EntityRoute("GET", "/threads/{thread_id}/messages"),
    EntityRoute("POST", "/threads/{thread_id}/messages", lambda ids: {"content": "hi"}),
]

ENTITY_PARAMS = (
    "{matter_id}",
    "{document_id}",
    "{review_id}",
    "{column_id}",
    "{run_id}",
    "{thread_id}",
)


def test_every_entity_route_is_covered() -> None:
    declared = {(r.method, r.template) for r in ENTITY_ROUTES}
    registered = {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute) and any(p in route.path for p in ENTITY_PARAMS)
        for method in route.methods or ()
    }
    missing = registered - declared
    assert not missing, f"entity routes without an isolation test: {sorted(missing)}"


async def make_ids(client: httpx.AsyncClient, actor: Actor, label: str) -> Ids:
    matter_id = await create_matter(client, actor, f"Project {label}")
    document_id = await create_document(client, actor, matter_id, sha256=label[0] * 64)
    r = await client.post(
        "/reviews",
        json={"matter_id": str(matter_id), "name": "R", "document_ids": [str(document_id)]},
        headers=actor.headers,
    )
    assert r.status_code == 201, r.text
    review_id = uuid.UUID(r.json()["id"])
    r = await client.post(f"/reviews/{review_id}/columns", json=COLUMN_BODY, headers=actor.headers)
    assert r.status_code == 201, r.text
    column_id = uuid.UUID(r.json()["id"])
    r = await client.post(f"/reviews/{review_id}/run", json={}, headers=actor.headers)
    assert r.status_code == 202, r.text
    run_id = uuid.UUID(r.json()["id"])
    t = await client.post(
        "/threads",
        json={"matter_id": str(matter_id), "document_ids": [str(document_id)]},
        headers=actor.headers,
    )
    assert t.status_code == 201, t.text
    return Ids(matter_id, document_id, review_id, column_id, run_id, uuid.UUID(t.json()["id"]))


@pytest.fixture
async def tenants(client: httpx.AsyncClient, make_actor: MakeActor) -> tuple[Actor, Actor, Ids]:
    alice = await make_actor("alice")
    bob = await make_actor("bob")
    return alice, bob, await make_ids(client, alice, "a")


@pytest.mark.parametrize("route", ENTITY_ROUTES, ids=lambda r: f"{r.method} {r.template}")
async def test_foreign_workspace_gets_404(
    client: httpx.AsyncClient,
    tenants: tuple[Actor, Actor, Ids],
    route: EntityRoute,
) -> None:
    alice, bob, ids = tenants
    path = route.path(ids)
    body = route.body(ids) if route.body else None

    # Control: the owner can reach it. Without this the test could pass on a
    # route that 404s for everyone.
    owner = await client.request(route.method, path, json=body, headers=alice.headers)
    assert owner.status_code != 404, f"owner got 404 on {route.method} {path}: {owner.text}"

    # Re-create for the mutating routes the control call may have consumed.
    if route.method == "DELETE":
        ids = await make_ids(client, alice, "c")
        path = route.path(ids)
        body = route.body(ids) if route.body else None

    foreign = await client.request(route.method, path, json=body, headers=bob.headers)
    assert foreign.status_code == 404, f"{route.method} {path} -> {foreign.status_code}"


async def test_list_endpoints_never_leak(
    client: httpx.AsyncClient, tenants: tuple[Actor, Actor, Ids]
) -> None:
    alice, bob, ids = tenants
    mine = await client.get("/matters", headers=alice.headers)
    theirs = await client.get("/matters", headers=bob.headers)
    assert [m["id"] for m in mine.json()] == [str(ids.matter_id)]
    assert theirs.json() == []
    assert (await client.get("/reviews", headers=bob.headers)).json() == []
    assert len((await client.get("/reviews", headers=alice.headers)).json()) == 1


async def test_token_naming_a_workspace_you_are_not_in_is_403(
    client: httpx.AsyncClient, tenants: tuple[Actor, Actor, Ids]
) -> None:
    alice, bob, ids = tenants
    # Bob forges a token claiming Alice's workspace. The signature is valid;
    # the membership row is not there.
    r = await client.get(f"/matters/{ids.matter_id}", headers=bob.token_for(alice.workspace_id))
    assert r.status_code == 403


async def test_token_without_workspace_is_400_on_scoped_routes(
    client: httpx.AsyncClient, make_actor: MakeActor
) -> None:
    alice = await make_actor("alice")
    r = await client.get("/matters", headers=alice.token_for(None))
    assert r.status_code == 400


async def test_missing_or_bad_token_is_401(client: httpx.AsyncClient) -> None:
    assert (await client.get("/matters")).status_code == 401
    assert (
        await client.get("/matters", headers={"Authorization": "Bearer not.a.jwt"})
    ).status_code == 401


def test_repository_refuses_entities_stamped_with_another_workspace() -> None:
    from unittest.mock import MagicMock

    from app.models.matter import Matter
    from app.repositories.matters import MatterRepository

    repo = MatterRepository(MagicMock(), uuid.uuid4())
    with pytest.raises(ValueError, match="stamped with workspace"):
        repo.add(Matter(workspace_id=uuid.uuid4(), name="smuggled"))
