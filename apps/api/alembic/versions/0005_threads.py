"""Assistant threads, thread documents, and messages.

Messages carry their verified citations as JSON plus verified/insufficient
flags; both tenant-owned tables carry workspace_id (rule 1).

Revision ID: 0005_threads
Revises: 0004_review
Create Date: 2026-09-08 11:18:07.256248
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_threads"
down_revision: str | None = "0004_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "threads",
        sa.Column("matter_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["matter_id"], ["matters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_threads_matter_id"), "threads", ["matter_id"], unique=False)
    op.create_index(op.f("ix_threads_workspace_id"), "threads", ["workspace_id"], unique=False)
    op.create_table(
        "messages",
        sa.Column("thread_id", sa.UUID(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("user", "assistant", name="messagerole", native_enum=False, length=12),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("insufficient", sa.Boolean(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=20), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_messages_thread_id"), "messages", ["thread_id"], unique=False)
    op.create_index(op.f("ix_messages_workspace_id"), "messages", ["workspace_id"], unique=False)
    op.create_table(
        "thread_documents",
        sa.Column("thread_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("thread_id", "document_id"),
    )


def downgrade() -> None:
    op.drop_table("thread_documents")
    op.drop_index(op.f("ix_messages_workspace_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_thread_id"), table_name="messages")
    op.drop_table("messages")
    op.drop_index(op.f("ix_threads_workspace_id"), table_name="threads")
    op.drop_index(op.f("ix_threads_matter_id"), table_name="threads")
    op.drop_table("threads")
