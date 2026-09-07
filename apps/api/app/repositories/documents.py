import uuid
from collections.abc import Sequence

from app.models.document import Document
from app.repositories.base import WorkspaceScopedRepository


class DocumentRepository(WorkspaceScopedRepository[Document]):
    model = Document

    async def list_for_matter(self, matter_id: uuid.UUID) -> Sequence[Document]:
        stmt = (
            self.scoped()
            .where(Document.matter_id == matter_id)
            .order_by(Document.created_at.desc())
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def find_duplicate(self, matter_id: uuid.UUID, sha256: str) -> Document | None:
        stmt = self.scoped().where(Document.matter_id == matter_id, Document.sha256 == sha256)
        return (await self.session.execute(stmt)).scalar_one_or_none()
