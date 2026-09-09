import httpx

from app.main import app


async def test_healthz_reports_ok() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_embed_dim_is_indexable_by_pgvector() -> None:
    """pgvector's HNSW and IVFFlat indexes cap at 2000 dimensions.

    text-embedding-3-large returns 3072 natively, so the ``dimensions``
    parameter must bring it under the cap. This guards the constant that the
    chunks.embedding column type is built from.
    """
    from app.config import get_settings

    assert get_settings().embed_dim <= 2000
