"""ORM models.

Every model added here must carry ``workspace_id`` unless it *is* the tenant
boundary (users, workspaces, memberships). Import each model module below so
Alembic autogenerate can see it.
"""

from app.db import Base
from app.models.document import Document, DocumentStatus
from app.models.matter import Matter
from app.models.user import User
from app.models.workspace import Membership, Role, Workspace

__all__ = [
    "Base",
    "Document",
    "DocumentStatus",
    "Matter",
    "Membership",
    "Role",
    "User",
    "Workspace",
]
