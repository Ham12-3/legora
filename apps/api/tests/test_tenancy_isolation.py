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
class EntityRoute:
    method: str
    template: str
    body: Callable[[uuid.UUID, uuid.UUID], dict[str, object]] | None = None

    def path(self, matter_id: uuid.UUID, document_id: uuid.UUID) -> str:
        return self.template.format(matter_id=matter_id, document_id=document_id)


def _presign_body(matter_id: uuid.UUID, document_id: uuid.UUID) -> dict[str, object]:
    return {"filename": "x.pdf", "mime_type": PDF, "size_bytes": 10, "sha256": "b" * 64}


def _register_body(matter_id: uuid.UUID, document_id: uuid.UUID) -> dict[str, object]:
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
    EntityRoute("DELETE", "/documents/{document_id}"),
]


def test_every_entity_route_is_covered() -> None:
    declared = {(r.method, r.template) for r in ENTITY_ROUTES}
    registered = {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute)
        and ("{matter_id}" in route.path or "{document_id}" in route.path)
        for method in route.methods or ()
    }
    missing = registered - declared
    assert not missing, f"entity routes without an isolation test: {sorted(missing)}"


@pytest.fixture
async def tenants(
    client: httpx.AsyncClient, make_actor: MakeActor
) -> tuple[Actor, Actor, uuid.UUID, uuid.UUID]:
    alice = await make_actor("alice")
    bob = await make_actor("bob")
    matter_id = await create_matter(client, alice)
    document_id = await create_document(client, alice, matter_id)
    return alice, bob, matter_id, document_id


@pytest.mark.parametrize("route", ENTITY_ROUTES, ids=lambda r: f"{r.method} {r.template}")
async def test_foreign_workspace_gets_404(
    client: httpx.AsyncClient,
    tenants: tuple[Actor, Actor, uuid.UUID, uuid.UUID],
    route: EntityRoute,
) -> None:
    alice, bob, matter_id, document_id = tenants
    path = route.path(matter_id, document_id)
    body = route.body(matter_id, document_id) if route.body else None

    # Control: the owner can reach it. Without this the test could pass on a
    # route that 404s for everyone.
    owner = await client.request(route.method, path, json=body, headers=alice.headers)
    assert owner.status_code != 404, f"owner got 404 on {route.method} {path}: {owner.text}"

    # Re-create for the mutating routes the control call may have consumed.
    if route.method == "DELETE":
        matter_id = await create_matter(client, alice, "Project Y")
        document_id = await create_document(client, alice, matter_id, sha256="c" * 64)
        path = route.path(matter_id, document_id)

    foreign = await client.request(route.method, path, json=body, headers=bob.headers)
    assert foreign.status_code == 404, f"{route.method} {path} -> {foreign.status_code}"


async def test_list_endpoints_never_leak(
    client: httpx.AsyncClient, tenants: tuple[Actor, Actor, uuid.UUID, uuid.UUID]
) -> None:
    alice, bob, matter_id, _ = tenants
    mine = await client.get("/matters", headers=alice.headers)
    theirs = await client.get("/matters", headers=bob.headers)
    assert [m["id"] for m in mine.json()] == [str(matter_id)]
    assert theirs.json() == []


async def test_token_naming_a_workspace_you_are_not_in_is_403(
    client: httpx.AsyncClient, tenants: tuple[Actor, Actor, uuid.UUID, uuid.UUID]
) -> None:
    alice, bob, matter_id, _ = tenants
    # Bob forges a token claiming Alice's workspace. The signature is valid;
    # the membership row is not there.
    r = await client.get(f"/matters/{matter_id}", headers=bob.token_for(alice.workspace_id))
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
