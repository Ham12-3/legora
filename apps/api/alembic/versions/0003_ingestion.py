"""Document pages and chunks: the parsed representation.

document_pages holds per-page text plus word geometry. chunks holds the
retrieval units with document-global offsets, a 1536-dim embedding under an
HNSW index (cosine), and a GIN index on to_tsvector(text) for the lexical
half of hybrid search. Both carry workspace_id (rule 1).

Revision ID: 0003_ingestion
Revises: 0002_tenancy
Create Date: 2026-09-07 20:34:38.543634
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_ingestion"
down_revision: str | None = "0002_tenancy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chunks",
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("section_path", sa.String(length=600), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("bboxes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(1536), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "ordinal", name="uq_chunks_doc_ordinal"),
    )
    op.create_index(op.f("ix_chunks_document_id"), "chunks", ["document_id"], unique=False)
    op.create_index(
        "ix_chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_chunks_text_fts",
        "chunks",
        [sa.literal_column("to_tsvector('english', text)")],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(op.f("ix_chunks_workspace_id"), "chunks", ["workspace_id"], unique=False)
    op.create_table(
        "document_pages",
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_offset", sa.Integer(), nullable=False),
        sa.Column("width", sa.Float(), nullable=False),
        sa.Column("height", sa.Float(), nullable=False),
        sa.Column("words", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_ocr", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "page_number", name="uq_pages_doc_num"),
    )
    op.create_index(
        op.f("ix_document_pages_document_id"), "document_pages", ["document_id"], unique=False
    )
    op.create_index(
        op.f("ix_document_pages_workspace_id"), "document_pages", ["workspace_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_document_pages_workspace_id"), table_name="document_pages")
    op.drop_index(op.f("ix_document_pages_document_id"), table_name="document_pages")
    op.drop_table("document_pages")
    op.drop_index(op.f("ix_chunks_workspace_id"), table_name="chunks")
    op.drop_index("ix_chunks_text_fts", table_name="chunks", postgresql_using="gin")
    op.drop_index(
        "ix_chunks_embedding_hnsw",
        table_name="chunks",
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_index(op.f("ix_chunks_document_id"), table_name="chunks")
    op.drop_table("chunks")
