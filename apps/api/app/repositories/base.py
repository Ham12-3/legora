"""Workspace-scoped repository base.

Rule 1 in CLAUDE.md lives here. A repository is constructed with the caller's
``workspace_id`` and every statement it builds carries
``WHERE workspace_id = :current``. Route handlers never write that filter
themselves, and a cross-workspace lookup is indistinguishable from a missing
row: both raise ``NotFoundError``.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped

from app.errors import NotFoundError


class ScopedModel(Protocol):
    """Structural shape of a tenant-owned model: the three mixins combined."""

    __tablename__: str
    id: Mapped[uuid.UUID]
    created_at: Mapped[datetime]
    workspace_id: Mapped[uuid.UUID]


class WorkspaceScopedRepository[ModelT: ScopedModel]:
    model: type[ModelT]

    def __init__(self, session: AsyncSession, workspace_id: uuid.UUID) -> None:
        self.session = session
        self.workspace_id = workspace_id

    # -- statement builders -------------------------------------------------

    def scoped(self) -> Select[tuple[ModelT]]:
        """The only way to start a SELECT on this model. Already filtered."""
        return select(self.model).where(self.model.workspace_id == self.workspace_id)

    # -- reads --------------------------------------------------------------

    async def get(self, entity_id: uuid.UUID) -> ModelT:
        result = await self.session.execute(self.scoped().where(self.model.id == entity_id))
        entity = result.scalar_one_or_none()
        if entity is None:
            raise NotFoundError(self.model.__tablename__.rstrip("s"))
        return entity

    async def list(self) -> Sequence[ModelT]:
        result = await self.session.execute(self.scoped().order_by(self.model.created_at.desc()))
        return result.scalars().all()

    # -- writes -------------------------------------------------------------

    def add(self, entity: ModelT) -> ModelT:
        """Attach a new entity, refusing anything not stamped with our workspace."""
        if entity.workspace_id != self.workspace_id:
            raise ValueError(
                f"{type(entity).__name__} stamped with workspace {entity.workspace_id}, "
                f"repository is scoped to {self.workspace_id}"
            )
        self.session.add(entity)
        return entity

    async def delete(self, entity_id: uuid.UUID) -> None:
        entity = await self.get(entity_id)
        await self.session.delete(entity)
