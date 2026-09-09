import uuid

from fastapi import APIRouter, status
from sqlalchemy import func, select

from app.auth.deps import CurrentPrincipal, DbSession
from app.models.document import Document
from app.models.matter import Matter
from app.repositories.matters import MatterRepository
from app.schemas.matters import MatterCreate, MatterOut

router = APIRouter(prefix="/matters", tags=["matters"])


async def _document_counts(session: DbSession, matter_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not matter_ids:
        return {}
    stmt = (
        select(Document.matter_id, func.count())
        .where(Document.matter_id.in_(matter_ids))
        .group_by(Document.matter_id)
    )
    return dict((await session.execute(stmt)).tuples().all())


def _to_out(matter: Matter, count: int) -> MatterOut:
    return MatterOut(
        id=matter.id,
        name=matter.name,
        description=matter.description,
        created_by=matter.created_by,
        created_at=matter.created_at,
        document_count=count,
    )


@router.get("", response_model=list[MatterOut])
async def list_matters(principal: CurrentPrincipal, session: DbSession) -> list[MatterOut]:
    repo = MatterRepository(session, principal.workspace_id)
    matters = await repo.list()
    counts = await _document_counts(session, [m.id for m in matters])
    return [_to_out(m, counts.get(m.id, 0)) for m in matters]


@router.post("", response_model=MatterOut, status_code=status.HTTP_201_CREATED)
async def create_matter(
    body: MatterCreate, principal: CurrentPrincipal, session: DbSession
) -> MatterOut:
    repo = MatterRepository(session, principal.workspace_id)
    matter = repo.add(
        Matter(
            workspace_id=principal.workspace_id,
            name=body.name,
            description=body.description,
            created_by=principal.user_id,
        )
    )
    await session.commit()
    await session.refresh(matter)
    return _to_out(matter, 0)


@router.get("/{matter_id}", response_model=MatterOut)
async def get_matter(
    matter_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> MatterOut:
    repo = MatterRepository(session, principal.workspace_id)
    matter = await repo.get(matter_id)
    counts = await _document_counts(session, [matter.id])
    return _to_out(matter, counts.get(matter.id, 0))


@router.delete("/{matter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_matter(
    matter_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> None:
    repo = MatterRepository(session, principal.workspace_id)
    await repo.delete(matter_id)
    await session.commit()
