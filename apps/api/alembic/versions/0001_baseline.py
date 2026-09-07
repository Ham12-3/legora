"""Baseline: required Postgres extensions.

No tables yet — those arrive in Phase 1. This revision exists so that a fresh
production database gets ``vector`` and ``pg_trgm`` without depending on the
local compose init script.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-07
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    # Extensions are left in place: dropping them would cascade into any
    # remaining vector columns.
    pass
