import uuid

import httpx

from tests.conftest import PDF, SHA_A, MakeActor, create_document, create_matter


async def test_presign_ticket_shape(client: httpx.AsyncClient, make_actor: MakeActor) -> None:
    alice = await make_actor("alice")
    matter_id = await create_matter(client, alice)

    r = await client.post(
        f"/matters/{matter_id}/documents/presign",
        json={"filename": "nda.pdf", "mime_type": PDF, "size_bytes": 10, "sha256": SHA_A},
        headers=alice.headers,
    )
    assert r.status_code == 200
    t = r.json()
    assert t["duplicate"] is False
    assert t["storage_key"] == (
        f"workspaces/{alice.workspace_id}/matters/{matter_id}/documents/{t['document_id']}"
    )
    assert t["upload_url"].startswith("http://localhost:9000/legora-documents/")
    assert "X-Amz-Signature" in t["upload_url"]


async def test_duplicate_sha_in_same_matter_is_reported_before_upload(
    client: httpx.AsyncClient, make_actor: MakeActor
) -> None:
    alice = await make_actor("alice")
    matter_id = await create_matter(client, alice)
    existing = await create_document(client, alice, matter_id)

    r = await client.post(
        f"/matters/{matter_id}/documents/presign",
        json={"filename": "copy.pdf", "mime_type": PDF, "size_bytes": 10, "sha256": SHA_A},
        headers=alice.headers,
    )
    assert r.status_code == 200
    assert r.json()["duplicate"] is True
    assert r.json()["document"]["id"] == str(existing)
    assert r.json()["upload_url"] is None


async def test_same_bytes_in_a_different_matter_is_not_a_duplicate(
    client: httpx.AsyncClient, make_actor: MakeActor
) -> None:
    alice = await make_actor("alice")
    m1 = await create_matter(client, alice, "Deal 1")
    m2 = await create_matter(client, alice, "Deal 2")
    d1 = await create_document(client, alice, m1)
    d2 = await create_document(client, alice, m2)
    assert d1 != d2


async def test_register_race_is_a_409(client: httpx.AsyncClient, make_actor: MakeActor) -> None:
    alice = await make_actor("alice")
    matter_id = await create_matter(client, alice)
    await create_document(client, alice, matter_id)

    # A second presign that raced ahead of the first registration.
    document_id = uuid.uuid4()
    r = await client.post(
        f"/matters/{matter_id}/documents",
        json={
            "document_id": str(document_id),
            "storage_key": (
                f"workspaces/{alice.workspace_id}/matters/{matter_id}/documents/{document_id}"
            ),
            "filename": "again.pdf",
            "mime_type": PDF,
            "size_bytes": 10,
            "sha256": SHA_A,
        },
        headers=alice.headers,
    )
    assert r.status_code == 409


async def test_register_rejects_spoofed_storage_key(
    client: httpx.AsyncClient, make_actor: MakeActor
) -> None:
    alice = await make_actor("alice")
    bob = await make_actor("bob")
    matter_id = await create_matter(client, alice)
    document_id = uuid.uuid4()

    r = await client.post(
        f"/matters/{matter_id}/documents",
        json={
            "document_id": str(document_id),
            # Points into Bob's prefix.
            "storage_key": f"workspaces/{bob.workspace_id}/matters/x/documents/{document_id}",
            "filename": "evil.pdf",
            "mime_type": PDF,
            "size_bytes": 10,
            "sha256": "d" * 64,
        },
        headers=alice.headers,
    )
    assert r.status_code == 400


async def test_unsupported_mime_and_oversize_are_rejected(
    client: httpx.AsyncClient, make_actor: MakeActor
) -> None:
    alice = await make_actor("alice")
    matter_id = await create_matter(client, alice)

    bad_type = await client.post(
        f"/matters/{matter_id}/documents/presign",
        json={
            "filename": "x.exe",
            "mime_type": "application/x-msdownload",
            "size_bytes": 10,
            "sha256": SHA_A,
        },
        headers=alice.headers,
    )
    assert bad_type.status_code == 422

    too_big = await client.post(
        f"/matters/{matter_id}/documents/presign",
        json={"filename": "x.pdf", "mime_type": PDF, "size_bytes": 10**12, "sha256": SHA_A},
        headers=alice.headers,
    )
    assert too_big.status_code == 413


async def test_list_status_and_download(client: httpx.AsyncClient, make_actor: MakeActor) -> None:
    alice = await make_actor("alice")
    matter_id = await create_matter(client, alice)
    doc = await create_document(client, alice, matter_id)

    listed = await client.get(f"/matters/{matter_id}/documents", headers=alice.headers)
    assert [d["id"] for d in listed.json()] == [str(doc)]
    assert listed.json()[0]["status"] == "uploaded"

    matter = await client.get(f"/matters/{matter_id}", headers=alice.headers)
    assert matter.json()["document_count"] == 1

    dl = await client.get(f"/documents/{doc}/download", headers=alice.headers)
    assert dl.status_code == 200
    assert "X-Amz-Signature" in dl.json()["url"]

    gone = await client.delete(f"/documents/{doc}", headers=alice.headers)
    assert gone.status_code == 204
    assert (await client.get(f"/documents/{doc}", headers=alice.headers)).status_code == 404
