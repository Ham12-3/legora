"""Database engine and session wiring.

Workspace scoping is *not* handled here. It is enforced in the repository base
class introduced in Phase 1 — see rule 1 in CLAUDE.md.
"""

from collections.abc import AsyncIterator

from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""


def create_engine() -> AsyncEngine:
    settings = get_settings()
    if settings.is_test:
        # pytest-asyncio gives each test its own event loop; a pooled asyncpg
        # connection created on one loop cannot be reused on the next.
        return create_async_engine(settings.database_url, poolclass=NullPool)
    return create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
    )


engine: AsyncEngine = create_engine()

SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a transactional session."""
    async with SessionLocal() as session:
        yield session
