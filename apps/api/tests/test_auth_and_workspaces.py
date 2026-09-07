import httpx

from tests.conftest import INTERNAL_HEADERS, MakeActor

REGISTER = {
    "email": "Carol@Example.com",
    "name": "Carol",
    "password": "a sufficiently long password",
    "workspace_name": "Carol & Co",
}


async def test_auth_endpoints_require_internal_secret(client: httpx.AsyncClient) -> None:
    assert (await client.post("/auth/register", json=REGISTER)).status_code == 401
    assert (
        await client.post(
            "/auth/login",
            json={"email": "x@y.z", "password": "p"},
            headers={"X-Internal-Secret": "wrong"},
        )
    ).status_code == 401


async def test_register_login_and_email_normalisation(client: httpx.AsyncClient) -> None:
    r = await client.post("/auth/register", json=REGISTER, headers=INTERNAL_HEADERS)
    assert r.status_code == 201
    assert r.json()["email"] == "carol@example.com"

    dup = await client.post("/auth/register", json=REGISTER, headers=INTERNAL_HEADERS)
    assert dup.status_code == 409

    ok = await client.post(
        "/auth/login",
        json={"email": "carol@example.com", "password": REGISTER["password"]},
        headers=INTERNAL_HEADERS,
    )
    assert ok.status_code == 200

    bad = await client.post(
        "/auth/login",
        json={"email": "carol@example.com", "password": "nope nope nope"},
        headers=INTERNAL_HEADERS,
    )
    assert bad.status_code == 401
    unknown = await client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": REGISTER["password"]},
        headers=INTERNAL_HEADERS,
    )
    assert unknown.status_code == 401
    assert bad.json() == unknown.json()


async def test_register_creates_owner_membership(
    client: httpx.AsyncClient, make_actor: MakeActor
) -> None:
    alice = await make_actor("alice")
    ws = await client.get("/workspace", headers=alice.headers)
    assert ws.status_code == 200
    body = ws.json()
    assert body["role"] == "owner"
    assert [m["email"] for m in body["members"]] == [alice.email]


async def test_member_management_respects_roles(
    client: httpx.AsyncClient, make_actor: MakeActor
) -> None:
    alice = await make_actor("alice")
    bob = await make_actor("bob")
    carol = await make_actor("carol")

    # Owner adds Bob as a plain member.
    r = await client.post("/workspace/members", json={"email": bob.email}, headers=alice.headers)
    assert r.status_code == 201
    assert r.json()["role"] == "member"

    # Bob, a member of Alice's workspace, cannot add Carol.
    r = await client.post(
        "/workspace/members",
        json={"email": carol.email},
        headers=bob.token_for(alice.workspace_id),
    )
    assert r.status_code == 403

    # Twice is a conflict.
    r = await client.post("/workspace/members", json={"email": bob.email}, headers=alice.headers)
    assert r.status_code == 409

    # Bob now sees two workspaces.
    me = await client.get("/me", headers=bob.headers)
    assert {w["role"] for w in me.json()["workspaces"]} == {"owner", "member"}


async def test_create_second_workspace(client: httpx.AsyncClient, make_actor: MakeActor) -> None:
    alice = await make_actor("alice")
    r = await client.post("/workspaces", json={"name": "Side Practice"}, headers=alice.headers)
    assert r.status_code == 201
    assert r.json()["role"] == "owner"
    listed = await client.get("/workspaces", headers=alice.token_for(None))
    assert len(listed.json()) == 2
