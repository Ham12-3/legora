"""ORM models.

Every model added here must carry ``workspace_id`` unless it *is* the tenant
boundary (users, workspaces, memberships) or a pure join table whose parents
both do (review_documents). Import each model module below so Alembic
autogenerate can see it.
"""

from app.db import Base
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.models.document_page import DocumentPage
from app.models.matter import Matter
from app.models.review import (
    Cell,
    CellCache,
    CellStatus,
    Citation,
    OutputType,
    Review,
    ReviewColumn,
    ReviewDocument,
    ReviewRun,
    RunMode,
    RunStatus,
)
from app.models.thread import Message, MessageRole, Thread, ThreadDocument
from app.models.user import User
from app.models.workspace import Membership, Role, Workspace

__all__ = [
    "Base",
    "Cell",
    "CellCache",
    "CellStatus",
    "Chunk",
    "Citation",
    "Document",
    "DocumentPage",
    "DocumentStatus",
    "Matter",
    "Membership",
    "Message",
    "MessageRole",
    "OutputType",
    "Review",
    "ReviewColumn",
    "ReviewDocument",
    "ReviewRun",
    "Role",
    "RunMode",
    "RunStatus",
    "Thread",
    "ThreadDocument",
    "User",
    "Workspace",
]
