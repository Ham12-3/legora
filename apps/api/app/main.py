"""FastAPI application entrypoint.

Rule 6 in CLAUDE.md: nothing here calls a model. Model calls belong in workers
or in explicitly streamed endpoints.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text

from app.config import get_settings
from app.db import SessionLocal
from app.errors import install_error_handlers
from app.queue import close_pool
from app.routers import auth, documents, matters, playbooks, reviews, threads, workspaces

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await close_pool()


app = FastAPI(
    title="Legora API",
    version="0.1.0",
    description="Ingestion, retrieval, and AI orchestration for legal document review.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

install_error_handlers(app)
app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(matters.router)
app.include_router(documents.router)
app.include_router(reviews.router)
app.include_router(threads.router)
app.include_router(playbooks.router)


class Health(BaseModel):
    status: Literal["ok"]
    environment: str
    version: str


class Readiness(BaseModel):
    status: Literal["ready", "degraded"]
    postgres: bool
    redis: bool


@app.get("/healthz", response_model=Health, tags=["ops"])
async def healthz() -> Health:
    """Liveness. Touches no dependency."""
    return Health(status="ok", environment=settings.environment, version=app.version)


@app.get("/readyz", response_model=Readiness, tags=["ops"])
async def readyz() -> Readiness:
    """Readiness. Actually reaches Postgres and Redis."""
    postgres_ok = False
    redis_ok = False

    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        postgres_ok = True
    except Exception:  # readiness reports failure, it does not raise
        postgres_ok = False

    client = Redis.from_url(settings.redis_url)
    try:
        redis_ok = bool(await client.ping())
    except Exception:
        redis_ok = False
    finally:
        await client.aclose()

    ready = postgres_ok and redis_ok
    return Readiness(
        status="ready" if ready else "degraded",
        postgres=postgres_ok,
        redis=redis_ok,
    )
