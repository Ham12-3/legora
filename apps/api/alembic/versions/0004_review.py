"""Tabular Review: reviews, columns, cells, citations, answer cache, runs.

Cells carry verified (bool): false means no quote survived string-matching
against the source. Citations are never stored unverified. cell_cache is
keyed by (document sha256, question, type, model, prompt version).

Revision ID: 0004_review
Revises: 0003_ingestion
Create Date: 2026-09-07 23:18:51.720608
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_review"
down_revision: str | None = "0003_ingestion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cell_cache",
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=20), nullable=False),
        sa.Column("answer", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("cache_key"),
    )
    op.create_table(
        "reviews",
        sa.Column("matter_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
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
    op.create_index(op.f("ix_reviews_matter_id"), "reviews", ["matter_id"], unique=False)
    op.create_index(op.f("ix_reviews_workspace_id"), "reviews", ["workspace_id"], unique=False)
    op.create_table(
        "review_columns",
        sa.Column("review_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column(
            "output_type",
            sa.Enum(
                "text",
                "boolean",
                "date",
                "money",
                "enum",
                name="outputtype",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("enum_options", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["review_id"], ["reviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_review_columns_review_id"), "review_columns", ["review_id"], unique=False
    )
    op.create_index(
        op.f("ix_review_columns_workspace_id"), "review_columns", ["workspace_id"], unique=False
    )
    op.create_table(
        "review_documents",
        sa.Column("review_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("row_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_id"], ["reviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("review_id", "document_id"),
    )
    op.create_table(
        "review_runs",
        sa.Column("review_id", sa.UUID(), nullable=False),
        sa.Column(
            "mode",
            sa.Enum("interactive", "batch", name="runmode", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "submitted",
                "done",
                "failed",
                name="runstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("total_cells", sa.Integer(), nullable=False),
        sa.Column("done_cells", sa.Integer(), nullable=False),
        sa.Column("targets", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("force", sa.Boolean(), nullable=False),
        sa.Column("provider_batch_id", sa.String(length=100), nullable=True),
        sa.Column("batch_plan", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["review_id"], ["reviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_review_runs_review_id"), "review_runs", ["review_id"], unique=False)
    op.create_index(
        op.f("ix_review_runs_workspace_id"), "review_runs", ["workspace_id"], unique=False
    )
    op.create_table(
        "cells",
        sa.Column("review_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("column_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "done",
                "failed",
                name="cellstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("not_found", sa.Boolean(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.String(length=10), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=20), nullable=True),
        sa.Column("cache_key", sa.String(length=64), nullable=True),
        sa.Column("from_cache", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["column_id"], ["review_columns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_id"], ["reviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_id", "document_id", "column_id", name="uq_cells_position"),
    )
    op.create_index(op.f("ix_cells_review_id"), "cells", ["review_id"], unique=False)
    op.create_index(op.f("ix_cells_workspace_id"), "cells", ["workspace_id"], unique=False)
    op.create_table(
        "citations",
        sa.Column("cell_id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=True),
        sa.Column("quoted_text", sa.Text(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("bboxes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("match_kind", sa.String(length=12), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["cell_id"], ["cells.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_citations_cell_id"), "citations", ["cell_id"], unique=False)
    op.create_index(op.f("ix_citations_workspace_id"), "citations", ["workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_citations_workspace_id"), table_name="citations")
    op.drop_index(op.f("ix_citations_cell_id"), table_name="citations")
    op.drop_table("citations")
    op.drop_index(op.f("ix_cells_workspace_id"), table_name="cells")
    op.drop_index(op.f("ix_cells_review_id"), table_name="cells")
    op.drop_table("cells")
    op.drop_index(op.f("ix_review_runs_workspace_id"), table_name="review_runs")
    op.drop_index(op.f("ix_review_runs_review_id"), table_name="review_runs")
    op.drop_table("review_runs")
    op.drop_table("review_documents")
    op.drop_index(op.f("ix_review_columns_workspace_id"), table_name="review_columns")
    op.drop_index(op.f("ix_review_columns_review_id"), table_name="review_columns")
    op.drop_table("review_columns")
    op.drop_index(op.f("ix_reviews_workspace_id"), table_name="reviews")
    op.drop_index(op.f("ix_reviews_matter_id"), table_name="reviews")
    op.drop_table("reviews")
    op.drop_table("cell_cache")
