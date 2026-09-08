"""Playbooks: a firm's standard positions, and the findings from checking a
document against them.

A finding says which position a clause matches (preferred, fallback,
unacceptable, or the topic is not addressed), how severe the deviation is,
and proposes replacement language. Its citation went through the same
verifier as grid cells; an unverified finding is stored with no citation and
``verified=false`` so the UI can say so.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import CreatedAt, UUIDPrimaryKey, WorkspaceScoped


def _varchar_enum(enum_cls: type[enum.StrEnum], length: int = 20) -> Enum:
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [m.value for m in e],
    )


class MatchedPosition(enum.StrEnum):
    PREFERRED = "preferred"
    FALLBACK = "fallback"
    UNACCEPTABLE = "unacceptable"
    NOT_ADDRESSED = "not_addressed"


class Severity(enum.StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PlaybookRunStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Playbook(UUIDPrimaryKey, WorkspaceScoped, CreatedAt, Base):
    __tablename__ = "playbooks"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    rules: Mapped[list["PlaybookRule"]] = relationship(
        back_populates="playbook", cascade="all, delete-orphan", order_by="PlaybookRule.ordinal"
    )


class PlaybookRule(UUIDPrimaryKey, WorkspaceScoped, CreatedAt, Base):
    __tablename__ = "playbook_rules"

    playbook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    preferred_position: Mapped[str] = mapped_column(Text, nullable=False)
    fallback_position: Mapped[str | None] = mapped_column(Text, nullable=True)
    unacceptable_position: Mapped[str | None] = mapped_column(Text, nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    playbook: Mapped[Playbook] = relationship(back_populates="rules")


class PlaybookRun(UUIDPrimaryKey, WorkspaceScoped, CreatedAt, Base):
    __tablename__ = "playbook_runs"

    playbook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[PlaybookRunStatus] = mapped_column(
        _varchar_enum(PlaybookRunStatus), nullable=False, default=PlaybookRunStatus.QUEUED
    )
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    findings: Mapped[list["Finding"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="Finding.ordinal"
    )


class Finding(UUIDPrimaryKey, WorkspaceScoped, Base):
    __tablename__ = "findings"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("playbook_rules.id", ondelete="SET NULL"), nullable=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    matched_position: Mapped[MatchedPosition] = mapped_column(
        _varchar_enum(MatchedPosition), nullable=False
    )
    severity: Mapped[Severity] = mapped_column(_varchar_enum(Severity), nullable=False)
    clause_reference: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    suggested_language: Mapped[str] = mapped_column(Text, nullable=False, default="")
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Verified citation, or null when no quote could be located.
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True
    )
    quoted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bboxes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    match_kind: Mapped[str | None] = mapped_column(String(12), nullable=True)

    run: Mapped[PlaybookRun] = relationship(back_populates="findings")
