"""Playbooks, rules, runs, and findings.

Findings store a verified citation (or none) plus verified/position/severity;
all four tables carry workspace_id (rule 1).

Revision ID: 0006_playbooks
Revises: 0005_threads
Create Date: 2026-09-08 11:51:21.190879
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_playbooks"
down_revision: str | None = "0005_threads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "playbooks",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_playbooks_workspace_id"), "playbooks", ["workspace_id"], unique=False)
    op.create_table(
        "playbook_rules",
        sa.Column("playbook_id", sa.UUID(), nullable=False),
        sa.Column("topic", sa.String(length=200), nullable=False),
        sa.Column("preferred_position", sa.Text(), nullable=False),
        sa.Column("fallback_position", sa.Text(), nullable=True),
        sa.Column("unacceptable_position", sa.Text(), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["playbook_id"], ["playbooks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_playbook_rules_playbook_id"), "playbook_rules", ["playbook_id"], unique=False
    )
    op.create_index(
        op.f("ix_playbook_rules_workspace_id"), "playbook_rules", ["workspace_id"], unique=False
    )
    op.create_table(
        "playbook_runs",
        sa.Column("playbook_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "done",
                "failed",
                name="playbookrunstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=20), nullable=True),
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
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["playbook_id"], ["playbooks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_playbook_runs_document_id"), "playbook_runs", ["document_id"], unique=False
    )
    op.create_index(
        op.f("ix_playbook_runs_playbook_id"), "playbook_runs", ["playbook_id"], unique=False
    )
    op.create_index(
        op.f("ix_playbook_runs_workspace_id"), "playbook_runs", ["workspace_id"], unique=False
    )
    op.create_table(
        "findings",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("rule_id", sa.UUID(), nullable=True),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(length=200), nullable=False),
        sa.Column(
            "matched_position",
            sa.Enum(
                "preferred",
                "fallback",
                "unacceptable",
                "not_addressed",
                name="matchedposition",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum("none", "low", "medium", "high", name="severity", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("clause_reference", sa.String(length=300), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("suggested_language", sa.Text(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=True),
        sa.Column("quoted_text", sa.Text(), nullable=True),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("bboxes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("match_kind", sa.String(length=12), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["playbook_rules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["playbook_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_findings_run_id"), "findings", ["run_id"], unique=False)
    op.create_index(op.f("ix_findings_workspace_id"), "findings", ["workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_findings_workspace_id"), table_name="findings")
    op.drop_index(op.f("ix_findings_run_id"), table_name="findings")
    op.drop_table("findings")
    op.drop_index(op.f("ix_playbook_runs_workspace_id"), table_name="playbook_runs")
    op.drop_index(op.f("ix_playbook_runs_playbook_id"), table_name="playbook_runs")
    op.drop_index(op.f("ix_playbook_runs_document_id"), table_name="playbook_runs")
    op.drop_table("playbook_runs")
    op.drop_index(op.f("ix_playbook_rules_workspace_id"), table_name="playbook_rules")
    op.drop_index(op.f("ix_playbook_rules_playbook_id"), table_name="playbook_rules")
    op.drop_table("playbook_rules")
    op.drop_index(op.f("ix_playbooks_workspace_id"), table_name="playbooks")
    op.drop_table("playbooks")
