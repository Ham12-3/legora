"""Test harness.

Tests run against a real Postgres (``legora_test`` on the compose instance):
the tenancy guarantees live in SQL and a SQLite stand-in would prove nothing.
The database is created on first run and migrated with Alembic, so the tests
exercise the same schema production gets. Every table is truncated after each
test.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

# Environment must be fixed before anything imports app.config.
os.environ["ENVIRONMENT"] = "test"
os.environ["INTERNAL_API_SECRET"] = "test-internal-secret-0123456789abcdef0123456789"
os.environ["STORAGE_ENABLED"] = "false"
os.environ["QUEUE_ENABLED"] = "false"
os.environ["EMBEDDINGS_PROVIDER"] = "fake"
# Tesseract is not a test dependency; the scanned fixture asserts the flag only.
os.environ["OCR_ENABLED"] = "false"
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://legora:legora@localhost:5432/legora_test"
)

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.auth.tokens import mint_internal_token
from app.config import get_settings
from app.db import SessionLocal
from app.main import app

TEST_DB_URL = get_settings().database_url
INTERNAL_HEADERS = {"X-Internal-Secret": os.environ["INTERNAL_API_SECRET"]}


async def _ensure_database() -> None:
    url = TEST_DB_URL
    db_name = url.rsplit("/", 1)[1]
    admin_url = url.rsplit("/", 1)[0] + "/postgres"
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        exists = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": db_name}
        )
        if exists.scalar_one_or_none() is None:
            await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """Sync on purpose: alembic's env.py calls asyncio.run itself."""
    asyncio.run(_ensure_database())
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture(autouse=True)
async def clean_tables() -> AsyncIterator[None]:
    yield
    # One retry: on a loaded Docker Desktop host the fresh connection this
    # needs occasionally times out, and that is not the test's fault.
    for attempt in (1, 2):
        try:
            async with SessionLocal() as session:
                await session.execute(
                    text(
                        "TRUNCATE messages, thread_documents, threads, "
                        "citations, cells, review_runs, review_columns, "
                        "review_documents, reviews, cell_cache, chunks, document_pages, "
                        "documents, matters, memberships, workspaces, users CASCADE"
                    )
                )
                await session.commit()
            break
        except (TimeoutError, OSError):
            if attempt == 2:
                raise
            await asyncio.sleep(2)


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# --- actors -----------------------------------------------------------------


@dataclass
class Actor:
    """A user with an active workspace and a token for it."""

    user_id: uuid.UUID
    workspace_id: uuid.UUID
    email: str
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def token_for(self, workspace_id: uuid.UUID | None) -> dict[str, str]:
        return {"Authorization": f"Bearer {mint_internal_token(self.user_id, workspace_id)}"}


MakeActor = Callable[[str], Awaitable[Actor]]


@pytest.fixture
def make_actor(client: httpx.AsyncClient) -> MakeActor:
    async def _make(label: str) -> Actor:
        email = f"{label}-{uuid.uuid4().hex[:8]}@example.com"
        r = await client.post(
            "/auth/register",
            json={
                "email": email,
                "name": label.title(),
                "password": "correct horse battery staple",
                "workspace_name": f"{label.title()} LLP",
            },
            headers=INTERNAL_HEADERS,
        )
        assert r.status_code == 201, r.text
        user_id = uuid.UUID(r.json()["id"])

        me = await client.get(
            "/me", headers={"Authorization": f"Bearer {mint_internal_token(user_id)}"}
        )
        assert me.status_code == 200, me.text
        workspace_id = uuid.UUID(me.json()["workspaces"][0]["id"])

        return Actor(
            user_id=user_id,
            workspace_id=workspace_id,
            email=email,
            token=mint_internal_token(user_id, workspace_id),
        )

    return _make


# --- fixtures for tenant-owned entities --------------------------------------

SHA_A = "a" * 64
PDF = "application/pdf"


async def create_matter(
    client: httpx.AsyncClient, actor: Actor, name: str = "Project X"
) -> uuid.UUID:
    r = await client.post("/matters", json={"name": name}, headers=actor.headers)
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["id"])


async def create_document(
    client: httpx.AsyncClient,
    actor: Actor,
    matter_id: uuid.UUID,
    *,
    sha256: str = SHA_A,
    filename: str = "msa.pdf",
    mime_type: str = PDF,
) -> uuid.UUID:
    ticket = await client.post(
        f"/matters/{matter_id}/documents/presign",
        json={"filename": filename, "mime_type": mime_type, "size_bytes": 1234, "sha256": sha256},
        headers=actor.headers,
    )
    assert ticket.status_code == 200, ticket.text
    t = ticket.json()
    assert t["duplicate"] is False, t

    r = await client.post(
        f"/matters/{matter_id}/documents",
        json={
            "document_id": t["document_id"],
            "storage_key": t["storage_key"],
            "filename": filename,
            "mime_type": mime_type,
            "size_bytes": 1234,
            "sha256": sha256,
        },
        headers=actor.headers,
    )
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["id"])
